"""High level diagnostics workflow built on top of the MSP transport."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from . import parsers
from .commands import MSPCommand
from .config import Profile
from .msp import MSPChecksumError, MSPClient, MSPTimeoutError, hexlify, le_i16


@dataclass(frozen=True)
class DiagConfig:
    """Resolved diagnostics configuration used by both CLI and GUI."""

    out_dir: Path
    baud: int
    imu_seconds: float
    status_samples: int
    profile_name: str
    ignore_tilt: bool
    max_tilt: float
    max_gyro_std: float
    max_gyro_bias: float
    max_acc_norm_std: float
    max_cyc_jitter: int
    max_i2c_errors: int
    jsonl: bool
    sample_rates: Mapping[str, float]

    @classmethod
    def from_profile(
        cls,
        *,
        out_dir: Path,
        baud: int,
        imu_seconds: float,
        status_samples: int,
        profile: Profile,
        jsonl: bool,
    ) -> "DiagConfig":
        sample_rates = {
            key: float(value)
            for key, value in profile.sample_rates.items()
            if isinstance(value, (int, float))
        }
        return cls(
            out_dir=out_dir,
            baud=baud,
            imu_seconds=imu_seconds,
            status_samples=status_samples,
            profile_name=profile.name,
            ignore_tilt=profile.ignore_tilt,
            max_tilt=profile.max_tilt,
            max_gyro_std=profile.max_gyro_std,
            max_gyro_bias=profile.max_gyro_bias,
            max_acc_norm_std=profile.max_accnorm_std,
            max_cyc_jitter=profile.max_cyc_jitter,
            max_i2c_errors=profile.max_i2c_errors,
            jsonl=jsonl,
            sample_rates=sample_rates,
        )

    def with_overrides(
        self,
        *,
        max_gyro_std: Optional[float] = None,
        max_gyro_bias: Optional[float] = None,
        max_accnorm_std: Optional[float] = None,
        max_cyc_jitter: Optional[int] = None,
        max_i2c_errors: Optional[int] = None,
        max_tilt: Optional[float] = None,
        ignore_tilt: Optional[bool] = None,
    ) -> "DiagConfig":
        updates = {}
        if max_gyro_std is not None:
            updates["max_gyro_std"] = float(max_gyro_std)
        if max_gyro_bias is not None:
            updates["max_gyro_bias"] = float(max_gyro_bias)
        if max_accnorm_std is not None:
            updates["max_acc_norm_std"] = float(max_accnorm_std)
        if max_cyc_jitter is not None:
            updates["max_cyc_jitter"] = int(max_cyc_jitter)
        if max_i2c_errors is not None:
            updates["max_i2c_errors"] = int(max_i2c_errors)
        if max_tilt is not None:
            updates["max_tilt"] = float(max_tilt)
        if ignore_tilt is not None:
            updates["ignore_tilt"] = bool(ignore_tilt)
        if not updates:
            return self
        return replace(self, **updates)

    def rate(self, name: str, default: float) -> float:
        value = self.sample_rates.get(name, default)
        return float(value) if value else default


def handshake(client: MSPClient) -> Tuple[Dict[str, object], Optional[str], List[str]]:
    """Perform the MSP handshake and return metadata, UID and reasons."""

    meta: Dict[str, object] = {"raw": {}}
    uid: Optional[str] = None
    reasons: List[str] = []

    def _record_raw(key: str, payload: bytes) -> None:
        meta.setdefault("raw", {})[key] = hexlify(payload)

    def _request(
        command: MSPCommand,
        *,
        reason: str,
        raw_key: str,
    ) -> Optional[bytes]:
        try:
            payload = client.request(command)
        except MSPTimeoutError:
            reasons.append(reason)
            return None
        except MSPChecksumError:
            reasons.append(f"{reason} (checksum)")
            return None
        _record_raw(raw_key, payload)
        return payload

    payload = _request(
        MSPCommand.MSP_API_VERSION,
        reason="no api version response",
        raw_key="MSP_API_VERSION",
    )
    if payload and len(payload) >= 3:
        meta["api_version"] = f"{payload[1]}.{payload[2]}.{payload[0]}"

    payload = _request(
        MSPCommand.MSP_FC_VARIANT,
        reason="no fc variant response",
        raw_key="MSP_FC_VARIANT",
    )
    if payload and len(payload) >= 4:
        meta["fc_variant"] = payload[:4].decode(errors="ignore")

    payload = _request(
        MSPCommand.MSP_FC_VERSION,
        reason="no fc version response",
        raw_key="MSP_FC_VERSION",
    )
    if payload and len(payload) >= 3:
        meta["fc_version"] = f"{payload[0]}.{payload[1]}.{payload[2]}"

    payload = _request(
        MSPCommand.MSP_BOARD_INFO,
        reason="no board info response",
        raw_key="MSP_BOARD_INFO",
    )
    if payload:
        if len(payload) >= 4:
            meta["board_id"] = payload[:4].decode(errors="ignore")
        if len(payload) >= 12:
            meta["board_uid"] = hexlify(payload[4:12])

    payload = _request(
        MSPCommand.MSP_BUILD_INFO,
        reason="no build info response",
        raw_key="MSP_BUILD_INFO",
    )
    if payload and len(payload) >= 26:
        build_date = payload[0:11].decode(errors="ignore")
        build_time = payload[11:19].decode(errors="ignore")
        git_short = payload[19:26].decode(errors="ignore")
        meta["build_info"] = f"{build_date} {build_time} {git_short}"

    payload = _request(
        MSPCommand.MSP_NAME,
        reason="no name response",
        raw_key="MSP_NAME",
    )
    if payload:
        meta["name"] = payload.decode(errors="ignore").strip("\x00")

    try:
        payload = client.request(MSPCommand.MSP_UID)
        if payload:
            uid = hexlify(payload)
            _record_raw("MSP_UID", payload)
    except MSPTimeoutError:
        # UID is optional; ignore to remain compatible with old firmware
        pass
    except MSPChecksumError:
        reasons.append("uid checksum error")

    return meta, uid, reasons


def collect_metrics(client: MSPClient, config: DiagConfig) -> Dict[str, object]:
    out: Dict[str, object] = {}
    status_samples = _collect_status_samples(client, config)
    if status_samples:
        out["loop_stats"] = _compute_loop_stats(status_samples)
    try:
        payload = client.request(MSPCommand.MSP_STATUS)
        out["status"] = parsers.parse_status(payload)
    except (MSPTimeoutError, MSPChecksumError):
        pass

    requests: Iterable[Tuple[MSPCommand, str, callable]] = (
        (MSPCommand.MSP_STATUS_EX, "status_ex", parsers.parse_status_ex),
        (MSPCommand.MSP_ATTITUDE, "attitude", parsers.parse_attitude),
        (MSPCommand.MSP_ALTITUDE, "altitude", parsers.parse_altitude),
        (MSPCommand.MSP_ANALOG, "analog", parsers.parse_analog),
        (MSPCommand.MSP_RC, "rc", parsers.parse_rc),
        (MSPCommand.MSP_MOTOR, "motors", parsers.parse_motors),
        (MSPCommand.MSP_VOLTAGE_METERS, "voltage_meters", parsers.parse_voltage_meters),
        (MSPCommand.MSP_CURRENT_METERS, "current_meters", parsers.parse_current_meters),
        (MSPCommand.MSP_BATTERY_STATE, "battery_state", parsers.parse_battery_state),
    )
    for command, key, parser_fn in requests:
        try:
            payload = client.request(command)
        except (MSPTimeoutError, MSPChecksumError):
            continue
        if payload:
            out[key] = parser_fn(payload)

    imu_stats = _collect_imu_statistics(client, config)
    if imu_stats:
        out["imu_stats"] = imu_stats

    return out


def _collect_status_samples(client: MSPClient, config: DiagConfig) -> List[int]:
    samples: List[int] = []
    interval = 1.0 / config.rate("status_hz", 10.0)
    for _ in range(config.status_samples):
        try:
            payload = client.request(MSPCommand.MSP_STATUS)
        except (MSPTimeoutError, MSPChecksumError):
            time.sleep(interval)
            continue
        parsed = parsers.parse_status(payload)
        value = parsed.get("cycleTime_us")
        if isinstance(value, int):
            samples.append(value)
        time.sleep(interval)
    return samples


def _compute_loop_stats(samples: List[int]) -> Dict[str, object]:
    mean = sum(samples) / len(samples)
    variance = sum((x - mean) ** 2 for x in samples) / len(samples)
    std = math.sqrt(variance)
    return {
        "samples": len(samples),
        "cycle_us_mean": round(mean, 2),
        "cycle_us_std": round(std, 3),
        "cycle_us_min": min(samples),
        "cycle_us_max": max(samples),
        "loop_hz_mean": round(1_000_000 / mean, 2) if mean else None,
    }


def _collect_imu_statistics(client: MSPClient, config: DiagConfig) -> Optional[Dict[str, object]]:
    end_time = time.time() + config.imu_seconds
    gyro: List[Tuple[int, int, int]] = []
    acc_norm: List[float] = []
    interval = 1.0 / config.rate("raw_imu_hz", 50.0)
    while time.time() < end_time:
        try:
            payload = client.request(MSPCommand.MSP_RAW_IMU, timeout=0.1)
        except (MSPTimeoutError, MSPChecksumError):
            time.sleep(interval)
            continue
        if len(payload) < 12:
            time.sleep(interval)
            continue
        ax = le_i16(payload[0:2])
        ay = le_i16(payload[2:4])
        az = le_i16(payload[4:6])
        gx = le_i16(payload[6:8])
        gy = le_i16(payload[8:10])
        gz = le_i16(payload[10:12])
        acc_norm.append(math.sqrt((ax / 512.0) ** 2 + (ay / 512.0) ** 2 + (az / 512.0) ** 2))
        gyro.append((gx, gy, gz))
        time.sleep(interval)
    if not gyro:
        return None

    def _stats(values: List[float]) -> Tuple[float, float]:
        mean_val = sum(values) / len(values)
        std_val = math.sqrt(sum((v - mean_val) ** 2 for v in values) / len(values))
        return mean_val, std_val

    gx_vals = [x for x, _, _ in gyro]
    gy_vals = [y for _, y, _ in gyro]
    gz_vals = [z for _, _, z in gyro]
    mean_x, std_x = _stats([float(x) for x in gx_vals])
    mean_y, std_y = _stats([float(y) for y in gy_vals])
    mean_z, std_z = _stats([float(z) for z in gz_vals])

    stats: Dict[str, object] = {
        "samples": len(gyro),
        "gyro_std": (
            round(std_x, 3),
            round(std_y, 3),
            round(std_z, 3),
        ),
        "gyro_bias": (
            round(mean_x, 3),
            round(mean_y, 3),
            round(mean_z, 3),
        ),
    }
    if acc_norm:
        _, acc_std = _stats(acc_norm)
        stats["acc_norm_std"] = round(acc_std, 3)
    return stats


def evaluate_thresholds(result: Dict[str, object], config: DiagConfig) -> List[str]:
    reasons: List[str] = []
    if not config.ignore_tilt:
        attitude = result.get("attitude", {})
        if isinstance(attitude, Mapping):
            roll = abs(attitude.get("roll_deg", 0))
            pitch = abs(attitude.get("pitch_deg", 0))
            if max(roll, pitch) > config.max_tilt:
                reasons.append(f"tilt>{config.max_tilt}deg (roll={roll}, pitch={pitch})")

    imu_stats = result.get("imu_stats")
    if isinstance(imu_stats, Mapping):
        gyro_std = imu_stats.get("gyro_std")
        if isinstance(gyro_std, (list, tuple)) and gyro_std:
            if max(abs(x) for x in gyro_std) > config.max_gyro_std:
                reasons.append(
                    "gyro_std>{limit} ({values})".format(
                        limit=config.max_gyro_std,
                        values=", ".join(map(str, gyro_std)),
                    )
                )
        gyro_bias = imu_stats.get("gyro_bias")
        if isinstance(gyro_bias, (list, tuple)) and gyro_bias:
            if max(abs(x) for x in gyro_bias) > config.max_gyro_bias:
                reasons.append(
                    "gyro_bias>{limit} ({values})".format(
                        limit=config.max_gyro_bias,
                        values=", ".join(map(str, gyro_bias)),
                    )
                )
        acc_std = imu_stats.get("acc_norm_std")
        if isinstance(acc_std, (int, float)) and acc_std > config.max_acc_norm_std:
            reasons.append(f"acc_norm_std>{config.max_acc_norm_std} ({acc_std})")

    status = result.get("status", {})
    if isinstance(status, Mapping):
        i2c_errors = status.get("i2c_errors")
        if isinstance(i2c_errors, int) and i2c_errors > config.max_i2c_errors:
            reasons.append(f"i2c_errors>{config.max_i2c_errors} ({i2c_errors})")

    loop_stats = result.get("loop_stats", {})
    if isinstance(loop_stats, Mapping):
        max_cycle = loop_stats.get("cycle_us_max")
        min_cycle = loop_stats.get("cycle_us_min")
        if isinstance(max_cycle, (int, float)) and isinstance(min_cycle, (int, float)):
            jitter = max_cycle - min_cycle
            if jitter > config.max_cyc_jitter:
                reasons.append(f"cycle_jitter>{config.max_cyc_jitter}us ({jitter})")

    return reasons


def chown_to_sudo_user(path: Path) -> None:
    if os.getuid() == 0 and "SUDO_UID" in os.environ and "SUDO_GID" in os.environ:
        try:
            os.chown(path, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
        except OSError:
            pass
    try:
        os.chmod(path, 0o664)
    except OSError:
        pass


def ensure_out_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o775)
    except OSError:
        pass


def write_result(out_dir: Path, payload: Dict[str, object]) -> Path:
    ensure_out_dir(out_dir)
    uid = payload.get("uid") or payload.get("meta", {}).get("board_uid")
    if isinstance(uid, str) and uid:
        filename = f"{uid}.json"
    else:
        filename = _allocate_defect_filename(out_dir)
    path = out_dir / filename
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    chown_to_sudo_user(path)
    return path


def write_summary(out_dir: Path, summaries: List[Dict[str, object]]) -> Path:
    ensure_out_dir(out_dir)
    path = out_dir / "_summary.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(summaries, handle, ensure_ascii=False, indent=2)
    chown_to_sudo_user(path)
    return path


def _allocate_defect_filename(out_dir: Path) -> str:
    for idx in range(1, 10000):
        candidate = out_dir / f"DEFECT-{idx:05d}.json"
        if not candidate.exists():
            return candidate.name
    return "DEFECT-OVERFLOW.json"


def summarise(result_path: Path, payload: Dict[str, object]) -> Dict[str, object]:
    meta = payload.get("meta", {})
    summary = {
        "port": payload.get("port"),
        "ok": payload.get("ok"),
        "uid": payload.get("uid", "—"),
        "fc": meta.get("fc_version"),
        "board": meta.get("board_id"),
        "file": str(result_path),
    }
    reasons = payload.get("reasons")
    if reasons:
        summary["reasons"] = reasons
    return summary


def diagnose_port(
    port: str,
    client: MSPClient,
    config: DiagConfig,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    started = time.time()
    result: Dict[str, object] = {
        "port": port,
        "baud": config.baud,
        "profile": config.profile_name,
        "ok": False,
        "reasons": [],
    }
    client.wake()
    meta, uid, handshake_reasons = handshake(client)
    result["meta"] = meta
    if uid:
        result["uid"] = uid
    result["reasons"].extend(handshake_reasons)
    metrics = collect_metrics(client, config)
    result.update(metrics)
    reasons = result.get("reasons", []) or []
    thresholds = evaluate_thresholds(result, config)
    reasons.extend(thresholds)
    result["reasons"] = reasons
    result["ok"] = len(reasons) == 0
    result["duration_s"] = round(time.time() - started, 3)
    path = write_result(config.out_dir, result)
    summary = summarise(path, result)
    return result, summary


__all__ = [
    "DiagConfig",
    "collect_metrics",
    "diagnose_port",
    "ensure_out_dir",
    "evaluate_thresholds",
    "handshake",
    "summarise",
    "write_result",
    "write_summary",
]
