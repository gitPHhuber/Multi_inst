"""Runtime primitives for managing diagnostic sessions."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

import serial

from ..io.json_writer import ReportWriter
from ..io.ports import PortFilterConfig, list_ports
from .analysis import ImuAnalyzer, LoopAnalyzer, evaluate
from .msp import open_serial_port, send_command
from .parsers import MSP_COMMANDS, MSPParseResult, parse_payload

log = logging.getLogger(__name__)


MSP_META_COMMANDS = [
    MSP_COMMANDS["MSP_API_VERSION"],
    MSP_COMMANDS["MSP_FC_VARIANT"],
    MSP_COMMANDS["MSP_FC_VERSION"],
    MSP_COMMANDS["MSP_BOARD_INFO"],
    MSP_COMMANDS["MSP_BUILD_INFO"],
    MSP_COMMANDS["MSP_UID"],
]

MSP_POLL_COMMANDS = [
    MSP_COMMANDS["MSP_STATUS"],
    MSP_COMMANDS["MSP_ATTITUDE"],
    MSP_COMMANDS["MSP_ANALOG"],
    MSP_COMMANDS["MSP_RAW_IMU"],
    MSP_COMMANDS["MSP_VOLTAGE_METERS"],
    MSP_COMMANDS["MSP_CURRENT_METERS"],
    MSP_COMMANDS["MSP_BATTERY_STATE"],
]


@dataclass
class ProbeResult:
    ok: bool
    uid: Optional[str]
    meta: Dict[str, str]
    api_version: Optional[str]
    reason: Optional[str] = None


def friendly_serial_error(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, PermissionError) or "Permission" in message:
        return "Нет прав (добавьте в dialout)"
    if "FileNotFoundError" in message or "No such file" in message:
        return "Порт недоступен"
    if "Device or resource busy" in message or "Resource busy" in message:
        return "Порт занят (ModemManager?)"
    if isinstance(exc, serial.SerialTimeoutException):
        return "Таймаут при обращении к порту"
    return message or "Неизвестная ошибка"


def probe_serial_port(port: str, baud: int, timeout: float = 0.3) -> ProbeResult:
    try:
        ser = open_serial_port(port, baudrate=baud, timeout=timeout)
    except (
        serial.SerialException,
        OSError,
        ValueError,
    ) as exc:  # pragma: no cover - depends on OS
        return ProbeResult(False, None, {}, None, friendly_serial_error(exc))
    try:
        meta: Dict[str, str] = {"port": port}
        uid: Optional[str] = None
        api_version: Optional[str] = None
        for cmd in MSP_META_COMMANDS:
            cmd_resp, payload, err = send_command(ser, cmd, timeout=timeout)
            if err:
                return ProbeResult(False, None, meta, api_version, f"MSP {cmd} {err}")
            result = parse_payload(cmd, payload)
            _attach_meta(meta, cmd, result)
            if cmd == MSP_COMMANDS["MSP_UID"]:
                uid = result.data.get("uid") if result else None
            if cmd == MSP_COMMANDS["MSP_API_VERSION"]:
                api_version = result.data.get("version") if result else None
        return ProbeResult(True, uid, meta, api_version, None)
    finally:
        try:
            ser.close()
        except Exception:  # pragma: no cover - cleanup best effort
            pass


def _attach_meta(meta: Dict[str, str], cmd: int, result: MSPParseResult) -> None:
    if cmd == MSP_COMMANDS["MSP_API_VERSION"]:
        meta["api_version"] = result.data.get("version", "0.0.0")
    elif cmd == MSP_COMMANDS["MSP_FC_VARIANT"]:
        meta["fc_variant"] = result.data.get("value", "")
    elif cmd == MSP_COMMANDS["MSP_FC_VERSION"]:
        meta["fc_version"] = result.data.get("value", "")
    elif cmd == MSP_COMMANDS["MSP_BOARD_INFO"]:
        meta["board_id"] = result.data.get("value", "")
    elif cmd == MSP_COMMANDS["MSP_BUILD_INFO"]:
        meta["build_info"] = result.data.get("value", "")
    elif cmd == MSP_COMMANDS["MSP_UID"]:
        meta["uid_raw"] = result.data.get("uid", "")


def _make_snapshot(port: str, uid: Optional[str], profile: str, mode: str) -> Dict:
    return {
        "uid": uid,
        "port": port,
        "profile": profile,
        "mode": mode,
        "ok": None,
        "reasons": [],
        "state": "idle",
        "meta": {},
        "status": {},
        "attitude": {},
        "analog": {},
        "imu": {},
        "loop": {},
        "raw_packets": [],
        "history": {
            "cycle_us": [],
            "loop_hz": [],
            "vbat": [],
            "amps": [],
        },
        "duration_s": 0.0,
        "updated": time.time(),
    }


@dataclass
class DeviceContext:
    uid: Optional[str]
    port: str
    profile: str
    mode: str
    auto: bool
    simulate: bool
    snapshot: Dict = field(default_factory=dict)
    meta: Dict[str, str] = field(default_factory=dict)
    history_cycle: Deque[float] = field(default_factory=lambda: deque(maxlen=600))
    history_loop_hz: Deque[float] = field(default_factory=lambda: deque(maxlen=600))
    history_vbat: Deque[float] = field(default_factory=lambda: deque(maxlen=600))
    history_amps: Deque[float] = field(default_factory=lambda: deque(maxlen=600))
    raw_packets: Deque[Dict] = field(default_factory=lambda: deque(maxlen=200))
    loop_analyzer: LoopAnalyzer = field(default_factory=LoopAnalyzer)
    imu_analyzer: ImuAnalyzer = field(default_factory=ImuAnalyzer)
    start_time: float = field(default_factory=time.time)
    last_status_i2c: Optional[int] = None
    last_status_ts: Optional[float] = None
    i2c_error_rate: float = 0.0
    task: Optional[asyncio.Task] = None
    completed: bool = False


class Session:
    def __init__(
        self,
        manager: "SessionManager",
        session_id: str,
        ports: List[str],
        baud: int,
        profile: str,
        mode: str,
        auto_flow: bool,
        simulate: bool,
        out_dir: str,
        whitelist_config: PortFilterConfig,
        test_duration: float = 5.0,
    ) -> None:
        self.manager = manager
        self.id = session_id
        self.baud = baud
        self.profile = profile
        self.mode = mode
        self.auto_flow = auto_flow
        self.simulate = simulate
        self.out_dir = out_dir
        self.test_duration = test_duration
        self.report_writer = ReportWriter(out_dir)
        self.port_filter = whitelist_config
        self.running = True
        self.contexts: Dict[str, DeviceContext] = {}
        self.snapshots: Dict[str, Dict] = {}
        self.completed_reports: Dict[str, Dict] = {}
        self.queue: asyncio.Queue[Dict] = asyncio.Queue(maxsize=256)
        self._requested_ports = ports
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while self.running:
            try:
                await self._scan()
            except Exception:  # pragma: no cover - defensive
                log.exception("error while scanning ports")
            await asyncio.sleep(0.5)

    async def _scan(self) -> None:
        ports = self._discover_ports()
        for port in ports:
            if port not in self.contexts:
                await self._attach_port(port)
        # remove disappeared ports
        for port in list(self.contexts):
            if port not in ports:
                await self._detach_port(port)

    def _discover_ports(self) -> List[str]:
        if self._requested_ports:
            return sorted(self._requested_ports)
        if self.simulate:
            # Provide deterministic simulated ports when simulation is enabled.
            return [f"sim://{idx:03d}" for idx in range(1, 1 + 3)]
        return [p.device for p in list_ports(self.port_filter)]

    async def _attach_port(self, port: str) -> None:
        if self.simulate or port.startswith("sim://"):
            uid = f"SIM-{port.split('/')[-1]}"
            ctx = DeviceContext(
                uid=uid,
                port=port,
                profile=self.profile,
                mode=self.mode,
                auto=self.auto_flow,
                simulate=True,
            )
            ctx.snapshot = _make_snapshot(port, uid, self.profile, self.mode)
            ctx.snapshot["state"] = "testing" if self.auto_flow else "ready"
            ctx.meta = {
                "fc_variant": "BTFL",
                "fc_version": "4.5.0",
                "board_id": "SIM",
                "build_info": "simulated",
                "api_version": "1.0.0",
            }
            ctx.snapshot["meta"] = ctx.meta
            self.contexts[port] = ctx
            if self.auto_flow:
                self._start_test(ctx)
            await self._publish(ctx)
            return

        result = await asyncio.get_running_loop().run_in_executor(
            None, probe_serial_port, port, self.baud
        )
        if not result.ok:
            await self._queue_event(
                {
                    "type": "probe_failed",
                    "port": port,
                    "reason": result.reason or "Unknown",
                }
            )
            return
        uid = result.uid or f"FC-{port.split('/')[-1]}"
        ctx = DeviceContext(
            uid=uid,
            port=port,
            profile=self.profile,
            mode=self.mode,
            auto=self.auto_flow,
            simulate=False,
        )
        ctx.meta = result.meta
        ctx.snapshot = _make_snapshot(port, uid, self.profile, self.mode)
        ctx.snapshot["meta"] = result.meta
        ctx.snapshot["state"] = "testing" if self.auto_flow else "ready"
        self.contexts[port] = ctx
        if self.auto_flow:
            self._start_test(ctx)
        await self._publish(ctx)

    async def _detach_port(self, port: str) -> None:
        ctx = self.contexts.pop(port, None)
        if not ctx:
            return
        if ctx.task and not ctx.task.done():
            ctx.task.cancel()
            try:
                await ctx.task
            except asyncio.CancelledError:
                pass
        await self._queue_event({"type": "removed", "port": port, "uid": ctx.uid})
        self.snapshots.pop(ctx.uid or port, None)

    def _start_test(self, ctx: DeviceContext) -> None:
        if ctx.task and not ctx.task.done():
            ctx.task.cancel()
        ctx.completed = False
        ctx.start_time = time.time()
        ctx.snapshot["state"] = "testing"
        if ctx.simulate:
            ctx.loop_analyzer = LoopAnalyzer()
            ctx.imu_analyzer = ImuAnalyzer()
            ctx.task = asyncio.create_task(self._run_simulated(ctx))
        else:
            ctx.loop_analyzer = LoopAnalyzer()
            ctx.imu_analyzer = ImuAnalyzer()
            ctx.task = asyncio.create_task(self._run_serial(ctx))

    async def retest(self, uid: str) -> None:
        for ctx in self.contexts.values():
            if ctx.uid == uid:
                self._start_test(ctx)
                await self._publish(ctx)
                return
        raise KeyError(uid)

    async def _run_simulated(self, ctx: DeviceContext) -> None:
        rng = random.Random(ctx.port)
        start = time.time()
        while self.running and (time.time() - start) < self.test_duration:
            await asyncio.sleep(0.1 if ctx.mode == "pro" else 0.2)
            ts = time.time()
            cycle_us = 250.0 + rng.gauss(0.0, 4.0)
            loop_hz = 1_000_000.0 / cycle_us if cycle_us else 0.0
            vbat = max(0.0, 16.2 - (ts - start) * 0.05)
            amps = abs(rng.gauss(0.2, 0.15))
            roll = rng.gauss(0.0, 1.5)
            pitch = rng.gauss(0.0, 1.5)
            gyro = (
                int(rng.gauss(0.0, 12.0)),
                int(rng.gauss(0.0, 12.0)),
                int(rng.gauss(0.0, 12.0)),
            )
            acc = (
                int(rng.gauss(0.0, 200)),
                int(rng.gauss(0.0, 200)),
                int(rng.gauss(16384.0, 400.0)),
            )
            ctx.loop_analyzer.add_sample(cycle_us, ts)
            ctx.imu_analyzer.add_sample(gyro, acc, ts)
            ctx.history_cycle.append(cycle_us)
            ctx.history_loop_hz.append(loop_hz)
            ctx.history_vbat.append(vbat)
            ctx.history_amps.append(amps)
            ctx.snapshot["status"] = {
                "cycleTime_us": cycle_us,
                "i2c_errors": 0,
            }
            ctx.snapshot["attitude"] = {
                "roll_deg": roll,
                "pitch_deg": pitch,
                "yaw_deg": rng.uniform(0, 360),
            }
            ctx.snapshot["analog"] = {
                "vbat_V": vbat,
                "amps_A": amps,
                "mAh_used": int((ts - start) * 120),
            }
            ctx.snapshot["imu"] = {
                "gyro_raw": gyro,
                "acc_raw": acc,
            }
            loop_stats = ctx.loop_analyzer.snapshot()
            imu_stats = ctx.imu_analyzer.snapshot(gyro_scale=1.0)
            analytics = evaluate(
                ctx.profile,
                loop_stats,
                imu_stats,
                ctx.i2c_error_rate,
                analog=ctx.snapshot["analog"],
                attitude=ctx.snapshot["attitude"],
            )
            ctx.snapshot["loop"] = loop_stats.__dict__ if loop_stats else {}
            ctx.snapshot["imu_stats"] = imu_stats.__dict__ if imu_stats else {}
            ctx.snapshot["ok"] = analytics.ok
            ctx.snapshot["reasons"] = analytics.reasons
            ctx.snapshot["duration_s"] = ts - ctx.start_time
            ctx.snapshot["history"] = {
                "cycle_us": list(ctx.history_cycle),
                "loop_hz": list(ctx.history_loop_hz),
                "vbat": list(ctx.history_vbat),
                "amps": list(ctx.history_amps),
            }
            ctx.snapshot["meta"] = ctx.meta
            ctx.snapshot["updated"] = ts
            self.snapshots[ctx.uid or ctx.port] = ctx.snapshot.copy()
            await self._publish(ctx)
        ctx.completed = True
        ctx.snapshot["state"] = "complete"
        self.snapshots[ctx.uid or ctx.port] = ctx.snapshot.copy()
        await self._publish(ctx)
        self._store_report(ctx)

    async def _run_serial(self, ctx: DeviceContext) -> None:
        try:
            ser = await asyncio.get_running_loop().run_in_executor(
                None, open_serial_port, ctx.port, self.baud, 0.1
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            ctx.snapshot["state"] = "error"
            ctx.snapshot["ok"] = False
            ctx.snapshot["reasons"] = [friendly_serial_error(exc)]
            await self._publish(ctx)
            return
        try:
            start = time.time()
            while self.running and (time.time() - start) < self.test_duration:
                ts = time.time()
                await asyncio.sleep(0.1 if ctx.mode == "pro" else 0.2)
                for cmd in MSP_POLL_COMMANDS:
                    (
                        cmd_resp,
                        payload,
                        err,
                    ) = await asyncio.get_running_loop().run_in_executor(
                        None, send_command, ser, cmd
                    )
                    if err:
                        ctx.snapshot.setdefault("errors", []).append(
                            {"cmd": cmd, "error": err, "ts": ts}
                        )
                        continue
                    parsed = parse_payload(cmd, payload)
                    self._update_from_payload(ctx, cmd, parsed, ts)
                    ctx.raw_packets.append(
                        {
                            "ts": ts,
                            "cmd": cmd,
                            "len": len(payload),
                            "payload_hex": payload.hex(),
                        }
                    )
                loop_stats = ctx.loop_analyzer.snapshot()
                imu_stats = ctx.imu_analyzer.snapshot(gyro_scale=1.0)
                analytics = evaluate(
                    ctx.profile,
                    loop_stats,
                    imu_stats,
                    ctx.i2c_error_rate,
                    analog=ctx.snapshot.get("analog"),
                    attitude=ctx.snapshot.get("attitude"),
                )
                ctx.snapshot["loop"] = loop_stats.__dict__ if loop_stats else {}
                ctx.snapshot["imu_stats"] = imu_stats.__dict__ if imu_stats else {}
                ctx.snapshot["ok"] = analytics.ok
                ctx.snapshot["reasons"] = analytics.reasons
                ctx.snapshot["duration_s"] = ts - ctx.start_time
                ctx.snapshot["history"] = {
                    "cycle_us": list(ctx.history_cycle),
                    "loop_hz": list(ctx.history_loop_hz),
                    "vbat": list(ctx.history_vbat),
                    "amps": list(ctx.history_amps),
                }
                ctx.snapshot["raw_packets"] = list(ctx.raw_packets)
                ctx.snapshot["updated"] = ts
                ctx.snapshot["state"] = "testing"
                self.snapshots[ctx.uid or ctx.port] = ctx.snapshot.copy()
                await self._publish(ctx)
        finally:
            try:
                ser.close()
            except Exception:  # pragma: no cover - cleanup
                pass
        ctx.completed = True
        ctx.snapshot["state"] = "complete"
        self.snapshots[ctx.uid or ctx.port] = ctx.snapshot.copy()
        await self._publish(ctx)
        self._store_report(ctx)

    def _update_from_payload(
        self, ctx: DeviceContext, cmd: int, parsed: MSPParseResult, ts: float
    ) -> None:
        if cmd == MSP_COMMANDS["MSP_STATUS"]:
            ctx.snapshot["status"] = parsed.data
            cycle = float(parsed.data.get("cycleTime_us", 0.0))
            if cycle:
                ctx.loop_analyzer.add_sample(cycle, ts)
                ctx.history_cycle.append(cycle)
                ctx.history_loop_hz.append(1_000_000.0 / cycle)
            i2c_errors = int(parsed.data.get("i2c_errors", 0))
            if ctx.last_status_i2c is not None and ctx.last_status_ts is not None:
                delta = i2c_errors - ctx.last_status_i2c
                dt = max(ts - ctx.last_status_ts, 1e-6)
                if delta >= 0:
                    ctx.i2c_error_rate = delta / dt
            ctx.last_status_i2c = i2c_errors
            ctx.last_status_ts = ts
        elif cmd == MSP_COMMANDS["MSP_ATTITUDE"]:
            ctx.snapshot["attitude"] = parsed.data
        elif cmd == MSP_COMMANDS["MSP_ANALOG"]:
            ctx.snapshot["analog"] = parsed.data
            vbat = float(parsed.data.get("vbat_V", 0.0))
            amps = float(parsed.data.get("amps_A", 0.0))
            ctx.history_vbat.append(vbat)
            ctx.history_amps.append(amps)
        elif cmd == MSP_COMMANDS["MSP_RAW_IMU"]:
            ctx.snapshot["imu"] = parsed.data
            gyro = parsed.data.get("gyro_raw")
            acc = parsed.data.get("acc_raw")
            if gyro and acc:
                ctx.imu_analyzer.add_sample(tuple(gyro), tuple(acc), ts)
        elif cmd in {
            MSP_COMMANDS["MSP_VOLTAGE_METERS"],
            MSP_COMMANDS["MSP_CURRENT_METERS"],
            MSP_COMMANDS["MSP_BATTERY_STATE"],
        }:
            key = {
                MSP_COMMANDS["MSP_VOLTAGE_METERS"]: "voltage_meters",
                MSP_COMMANDS["MSP_CURRENT_METERS"]: "current_meters",
                MSP_COMMANDS["MSP_BATTERY_STATE"]: "battery_state",
            }[cmd]
            ctx.snapshot[key] = parsed.data

    async def _publish(self, ctx: DeviceContext) -> None:
        await self._queue_event(
            {
                "type": "snapshot",
                "uid": ctx.uid or ctx.port,
                "data": ctx.snapshot,
            }
        )

    async def _queue_event(self, event: Dict) -> None:
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self.queue.put(event)

    def snapshot(self) -> List[Dict]:
        return [ctx.snapshot for ctx in self.contexts.values()]

    def _store_report(self, ctx: DeviceContext) -> None:
        try:
            self.report_writer.write_report(ctx.uid, ctx.snapshot)
        except Exception:  # pragma: no cover - filesystem dependent
            log.exception("failed to write report for %s", ctx.uid)
        uid = ctx.uid or ctx.port
        self.completed_reports[uid] = ctx.snapshot.copy()
        if self.manager:
            self.manager.reports[uid] = ctx.snapshot.copy()

    async def stop(self) -> None:
        self.running = False
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        for ctx in list(self.contexts.values()):
            if ctx.task and not ctx.task.done():
                ctx.task.cancel()
                try:
                    await ctx.task
                except asyncio.CancelledError:
                    pass
        try:
            self.report_writer.write_summary()
        except Exception:  # pragma: no cover - filesystem dependent
            log.exception("failed to write session summary")


class SessionManager:
    def __init__(self) -> None:
        self.sessions: Dict[str, Session] = {}
        self.reports: Dict[str, Dict] = {}

    def start_session(
        self,
        ports: List[str],
        baud: int,
        profile: str,
        mode: str,
        auto_flow: bool,
        simulate: bool,
        out_dir: str,
        whitelist_config: PortFilterConfig,
        test_duration: float = 5.0,
    ) -> Session:
        session_id = f"session-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
        session = Session(
            self,
            session_id,
            ports,
            baud,
            profile,
            mode,
            auto_flow,
            simulate,
            out_dir,
            whitelist_config,
            test_duration,
        )
        self.sessions[session_id] = session
        return session

    async def stop_session(self, session_id: str) -> None:
        session = self.sessions.pop(session_id, None)
        if session:
            await session.stop()

    def get_session(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError(session_id)
        return session
