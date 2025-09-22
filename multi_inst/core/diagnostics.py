"""High level diagnostics workflow built on top of the MSP transport."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import parsers
from .commands import MSPCommand
from .msp import MSPChecksumError, MSPClient, MSPTimeoutError, hexlify, le_i16


@dataclass
class DiagConfig:
    out_dir: Path
    baud: int = 1_000_000
    imu_seconds: float = 3.0
    status_samples: int = 50
    max_gyro_std: float = 6.0
    max_cyc_jitter: int = 10
    max_i2c_errors: int = 0
    max_tilt: float = 5.0
    ignore_tilt: bool = False
    jsonl: bool = False


def handshake(client: MSPClient) -> Dict[str, object]:
    info: Dict[str, object] = {}
    try:
        payload = client.request(MSPCommand.MSP_API_VERSION)
        if len(payload) >= 3:
            info["api_version"] = f"{payload[1]}.{payload[2]}.{payload[0]}"
            info["api_raw"] = hexlify(payload)
    except MSPTimeoutError:
        info.setdefault("reasons", []).append("no api version response")
    except MSPChecksumError:
        info.setdefault("reasons", []).append("api version checksum error")

    try:
        payload = client.request(MSPCommand.MSP_FC_VARIANT)
        if len(payload) >= 4:
            info["fc_variant"] = payload[:4].decode(errors="ignore")
    except (MSPTimeoutError, MSPChecksumError):
        info.setdefault("reasons", []).append("no fc variant response")

    try:
        payload = client.request(MSPCommand.MSP_FC_VERSION)
        if len(payload) >= 3:
            info["fc_version"] = f"{payload[0]}.{payload[1]}.{payload[2]}"
    except (MSPTimeoutError, MSPChecksumError):
        info.setdefault("reasons", []).append("no fc version response")

    try:
        payload = client.request(MSPCommand.MSP_BOARD_INFO)
        if len(payload) >= 4:
            info["board_id"] = payload[:4].decode(errors="ignore")
        if len(payload) >= 12:
            info["board_uid"] = hexlify(payload[4:12])
    except (MSPTimeoutError, MSPChecksumError):
        info.setdefault("reasons", []).append("no board info response")

    try:
        payload = client.request(MSPCommand.MSP_BUILD_INFO)
        if len(payload) >= 26:
            build_date = payload[0:11].decode(errors="ignore")
            build_time = payload[11:19].decode(errors="ignore")
            git_short = payload[19:26].decode(errors="ignore")
            info["build_info"] = f"{build_date} {build_time} {git_short}"
    except (MSPTimeoutError, MSPChecksumError):
        info.setdefault("reasons", []).append("no build info response")

    try:
        payload = client.request(MSPCommand.MSP_UID)
        if payload:
            info["uid"] = hexlify(payload)
    except MSPTimeoutError:
        # UID is optional; ignore timeouts silently to avoid flagging older firmware
        pass

    return info


def collect_metrics(client: MSPClient, config: DiagConfig) -> Dict[str, object]:
    out: Dict[str, object] = {}
    status_samples = _collect_status_samples(client, config.status_samples)
    if status_samples:
        out["loop_stats"] = _compute_loop_stats(status_samples)
        try:
            payload = client.request(MSPCommand.MSP_STATUS)
            out["status"] = parsers.parse_status(payload)
        except (MSPTimeoutError, MSPChecksumError):
            pass

    for cmd, key, parser in (
        (MSPCommand.MSP_ATTITUDE, "attitude", parsers.parse_attitude),
        (MSPCommand.MSP_ALTITUDE, "altitude", parsers.parse_altitude),
        (MSPCommand.MSP_ANALOG, "analog", parsers.parse_analog),
        (MSPCommand.MSP_RC, "rc", parsers.parse_rc),
        (MSPCommand.MSP_MOTOR, "motors", parsers.parse_motors),
        (MSPCommand.MSP_VOLTAGE_METERS, "voltage_meters", parsers.parse_voltage_meters),
        (MSPCommand.MSP_CURRENT_METERS, "current_meters", parsers.parse_current_meters),
        (MSPCommand.MSP_BATTERY_STATE, "battery_state", parsers.parse_battery_state),
    ):
        try:
            payload = client.request(cmd)
        except (MSPTimeoutError, MSPChecksumError):
            continue
        if payload:
            out[key] = parser(payload)
            if key == "analog" and "vbat_V" in out[key]:
                out["vbat_V"] = out[key]["vbat_V"]

    imu_stats = _collect_imu_statistics(client, config.imu_seconds)
    if imu_stats:
        out["imu_stats"] = imu_stats

    return out


def _collect_status_samples(client: MSPClient, count: int) -> List[int]:
    samples: List[int] = []
    for _ in range(count):
        try:
            payload = client.request(MSPCommand.MSP_STATUS)
        except (MSPTimeoutError, MSPChecksumError):
            continue
        parsed = parsers.parse_status(payload)
        value = parsed.get("cycleTime_us")
        if isinstance(value, int):
            samples.append(value)
        time.sleep(0.01)
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


def _collect_imu_statistics(client: MSPClient, duration: float) -> Optional[Dict[str, object]]:
    end_time = time.time() + duration
    gyro: List[Tuple[int, int, int]] = []
    acc_norm: List[float] = []
    while time.time() < end_time:
        try:
            payload = client.request(MSPCommand.MSP_RAW_IMU, timeout=0.1)
        except (MSPTimeoutError, MSPChecksumError):
            time.sleep(0.01)
            continue
        if len(payload) < 12:
            continue
        ax = le_i16(payload[0:2])
        ay = le_i16(payload[2:4])
        az = le_i16(payload[4:6])
        gx = le_i16(payload[6:8])
        gy = le_i16(payload[8:10])
        gz = le_i16(payload[10:12])
        acc_norm.append(math.sqrt((ax / 512.0) ** 2 + (ay / 512.0) ** 2 + (az / 512.0) ** 2))
        gyro.append((gx, gy, gz))
        time.sleep(0.01)
    if not gyro:
        return None
    gx_vals = [x for x, _, _ in gyro]
    gy_vals = [y for _, y, _ in gyro]
    gz_vals = [z for _, _, z in gyro]

    def _stdev(values: List[float]) -> float:
        mean = sum(values) / len(values)
        return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))

    stats: Dict[str, object] = {
        "samples": len(gyro),
        "gyro_std": (
            round(_stdev(gx_vals), 3),
            round(_stdev(gy_vals), 3),
            round(_stdev(gz_vals), 3),
        ),
    }
    if acc_norm:
        stats["acc_norm_std"] = round(_stdev(acc_norm), 3)
    return stats


def evaluate_thresholds(result: Dict[str, object], config: DiagConfig) -> List[str]:
    reasons: List[str] = []
    if not config.ignore_tilt:
        attitude = result.get("attitude", {})
        roll = abs(attitude.get("roll_deg", 0))
        pitch = abs(attitude.get("pitch_deg", 0))
        if max(roll, pitch) > config.max_tilt:
            reasons.append(f"tilt>{config.max_tilt}deg (roll={roll}, pitch={pitch})")
    imu_stats = result.get("imu_stats", {})
    gyro_std = imu_stats.get("gyro_std") if isinstance(imu_stats, dict) else None
    if isinstance(gyro_std, (list, tuple)):
        if max(abs(x) for x in gyro_std) > config.max_gyro_std:
            reasons.append(
                f"gyro_std>{config.max_gyro_std} ({gyro_std[0]}, {gyro_std[1]}, {gyro_std[2]})"
            )
    status = result.get("status", {})
    i2c_errors = status.get("i2c_errors") if isinstance(status, dict) else None
    if isinstance(i2c_errors, int) and i2c_errors > config.max_i2c_errors:
        reasons.append(f"i2c_errors>{config.max_i2c_errors} ({i2c_errors})")
    loop_stats = result.get("loop_stats", {})
    if isinstance(loop_stats, dict):
        jitter = loop_stats.get("cycle_us_max")
        min_cycle = loop_stats.get("cycle_us_min")
        if isinstance(jitter, (int, float)) and isinstance(min_cycle, (int, float)):
            diff = jitter - min_cycle
            if diff > config.max_cyc_jitter:
                reasons.append(f"cycle_jitter>{config.max_cyc_jitter}us ({diff})")
    return reasons


def apply_permissions(path: Path, mode: int) -> None:
    if os.getuid() == 0 and "SUDO_UID" in os.environ and "SUDO_GID" in os.environ:
        try:
            os.chown(path, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
        except OSError:
            pass
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def ensure_out_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    apply_permissions(path, 0o775)


def write_result(out_dir: Path, payload: Dict[str, object]) -> Path:
    ensure_out_dir(out_dir)
    uid = payload.get("uid") or payload.get("board_uid")
    if isinstance(uid, str) and uid:
        filename = f"{uid}.json"
    else:
        filename = _allocate_defect_filename(out_dir)
    path = out_dir / filename
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    apply_permissions(path, 0o664)
    return path


def write_summary(out_dir: Path, summaries: List[Dict[str, object]]) -> Path:
    ensure_out_dir(out_dir)
    path = out_dir / "_summary.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(summaries, handle, ensure_ascii=False, indent=2)
    apply_permissions(path, 0o664)
    return path


def _allocate_defect_filename(out_dir: Path) -> str:
    for idx in range(1, 10000):
        candidate = out_dir / f"DEFECT-{idx:05d}.json"
        if not candidate.exists():
            return candidate.name
    return "DEFECT-OVERFLOW.json"


def summarise(result_path: Path, payload: Dict[str, object]) -> Dict[str, object]:
    summary = {
        "port": payload.get("port"),
        "ok": payload.get("ok"),
        "uid": payload.get("uid", "—"),
        "fc": payload.get("fc_version"),
        "board": payload.get("board_id"),
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
        "ok": False,
        "reasons": [],
    }
    client.wake()
    result.update(handshake(client))
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
