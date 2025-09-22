"""Data source abstractions for the GUI."""

from __future__ import annotations

import math
import queue
import random
import threading
import time
from typing import Dict, Iterable, List, Optional

try:  # pragma: no cover - optional dependency for GUI usage only
    import serial  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    serial = None  # type: ignore[assignment]

from multi_inst.core.commands import MSPCommand
from multi_inst.core.msp import MSPClient, MSPChecksumError, MSPTimeoutError, hexlify, le_i16
from multi_inst.core import parsers

from .data_models import DeviceIdentity, TelemetryFrame


class TelemetryQueue(queue.Queue[TelemetryFrame]):
    """Simple typed queue with a helper to fetch the latest value."""

    def pop_latest(self) -> Optional[TelemetryFrame]:
        latest: Optional[TelemetryFrame] = None
        try:
            while True:
                latest = self.get_nowait()
        except queue.Empty:
            pass
        return latest


class DeviceSource:
    """Base class for telemetry sources."""

    def __init__(self, identity: DeviceIdentity, *, target_hz: float) -> None:
        self.identity = identity
        self.queue = TelemetryQueue(maxsize=20)
        self.target_hz = target_hz

    def start(self) -> None:  # pragma: no cover - runtime behaviour
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - runtime behaviour
        raise NotImplementedError


class SimulatedSource(DeviceSource):
    """Deterministic sine/cosine generator for GUI demos."""

    def __init__(self, identity: DeviceIdentity, *, target_hz: float = 30.0) -> None:
        super().__init__(identity, target_hz=target_hz)
        self.queue = TelemetryQueue(maxsize=10)
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._phase = random.random() * math.pi

    def start(self) -> None:  # pragma: no cover - runtime behaviour
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:  # pragma: no cover - runtime behaviour
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:  # pragma: no cover - runtime behaviour
        next_tick = time.time()
        while self._running.is_set():
            now = time.time()
            dt = now - next_tick
            if dt >= 0:
                self.queue.put(self._generate_frame(now))
                next_tick = now + 1.0 / max(1.0, self.target_hz)
            time.sleep(0.002)

    def _generate_frame(self, timestamp: float) -> TelemetryFrame:
        t = timestamp + self._phase
        roll = math.sin(t) * 5.0
        pitch = math.cos(t * 0.7) * 4.0
        yaw = math.sin(t * 0.5) * 180
        hz = 400 + math.sin(t * 1.8) * 20
        vbat = 15.5 + math.sin(t * 0.2) * 0.3
        amps = 10 + math.sin(t * 0.4) * 2.5
        mAh = 1200 + (timestamp % 600) * 5
        raw_imu = {
            "ax": math.sin(t * 1.5) * 512,
            "ay": math.cos(t * 1.1) * 512,
            "az": 1.0 * 512,
            "gx": math.sin(t * 2.5) * 1000,
            "gy": math.cos(t * 2.2) * 1000,
            "gz": math.sin(t * 0.8) * 1000,
        }
        return TelemetryFrame(
            timestamp=timestamp,
            status={"cycleTime_us": int(1_000_000 / hz), "i2c_errors": 0},
            attitude={"roll_deg": roll, "pitch_deg": pitch, "yaw_deg": yaw},
            altitude={"estimated_altitude_m": math.sin(t * 0.3) * 1.5},
            analog={"vbat_V": vbat, "amperage_A": amps, "mAh_drawn": mAh},
            rc={"channels": [1500 + math.sin(t) * 200 for _ in range(8)]},
            motors={"throttle": 1500 + math.sin(t * 1.2) * 200},
            voltage_meters=[{"id": 0, "voltage_V": vbat}],
            current_meters=[{"id": 0, "current_A": amps}],
            battery_state={"cell_count": 4, "mah_drawn": mAh, "capacity_mah": 1800},
            raw_imu=raw_imu,
            raw_packets={}
        )


class LiveSerialSource(DeviceSource):
    """Poll telemetry from a live MSP device using :class:`MSPClient`."""

    POLL_COMMANDS: Iterable[tuple[MSPCommand, str]] = (
        (MSPCommand.MSP_STATUS, "status"),
        (MSPCommand.MSP_ATTITUDE, "attitude"),
        (MSPCommand.MSP_ALTITUDE, "altitude"),
        (MSPCommand.MSP_ANALOG, "analog"),
        (MSPCommand.MSP_RC, "rc"),
        (MSPCommand.MSP_MOTOR, "motors"),
        (MSPCommand.MSP_VOLTAGE_METERS, "voltage_meters"),
        (MSPCommand.MSP_CURRENT_METERS, "current_meters"),
        (MSPCommand.MSP_BATTERY_STATE, "battery_state"),
        (MSPCommand.MSP_RAW_IMU, "raw_imu"),
    )

    def __init__(
        self,
        identity: DeviceIdentity,
        *,
        port: str,
        baud: int = 1_000_000,
        target_hz: float = 30.0,
        timeout: float = 0.15,
    ) -> None:
        super().__init__(identity, target_hz=target_hz)
        self.queue = TelemetryQueue(maxsize=20)
        self._port = port
        self._baud = baud
        self._timeout = timeout
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._client: Optional[MSPClient] = None

    def start(self) -> None:  # pragma: no cover - runtime behaviour
        if serial is None:
            raise RuntimeError("pyserial is required for live telemetry")
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:  # pragma: no cover - runtime behaviour
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._client:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 - best effort shutdown
                pass
            self._client = None

    # The heavy lifting happens in a thread to keep the Qt loop responsive.
    def _run(self) -> None:  # pragma: no cover - runtime behaviour
        assert serial is not None
        while self._running.is_set():
            try:
                with serial.Serial(self._port, baudrate=self._baud, timeout=self._timeout) as handle:
                    client = MSPClient(handle, inter_command_gap=0.01, retries=2)
                    client.wake()
                    self._client = client
                    self._poll_loop(client)
            except serial.SerialException:
                time.sleep(1.0)
            finally:
                self._client = None

    def _poll_loop(self, client: MSPClient) -> None:  # pragma: no cover - runtime behaviour
        interval = 1.0 / max(self.target_hz, 1.0)
        next_tick = time.time()
        while self._running.is_set():
            now = time.time()
            if now >= next_tick:
                frame = self._collect_frame(client, now)
                if frame:
                    self.queue.put(frame)
                next_tick = now + interval
            time.sleep(0.002)

    def _collect_frame(self, client: MSPClient, timestamp: float) -> Optional[TelemetryFrame]:
        payloads: Dict[str, object] = {}
        raw_packets: Dict[str, str] = {}
        for command, attr in self.POLL_COMMANDS:
            try:
                payload = client.request(command, timeout=self._timeout)
            except (MSPTimeoutError, MSPChecksumError):
                continue
            if payload is None:
                continue
            raw_packets[attr] = hexlify(payload)
            parser = getattr(parsers, f"parse_{attr}", None)
            if callable(parser):
                parsed = parser(payload)
            elif attr == "raw_imu":
                parsed = self._parse_raw_imu(payload)
            else:
                parsed = {"raw": payload}
            payloads[attr] = parsed
        if not payloads:
            return None
        return TelemetryFrame(timestamp=timestamp, raw_packets=raw_packets, **payloads)

    @staticmethod
    def _parse_raw_imu(payload: bytes) -> Dict[str, float]:
        if len(payload) < 18:
            return {}
        return {
            "ax": le_i16(payload[0:2]),
            "ay": le_i16(payload[2:4]),
            "az": le_i16(payload[4:6]),
            "gx": le_i16(payload[6:8]),
            "gy": le_i16(payload[8:10]),
            "gz": le_i16(payload[10:12]),
        }


def build_simulated_sources(count: int = 2) -> List[SimulatedSource]:
    sources: List[SimulatedSource] = []
    for idx in range(count):
        identity = DeviceIdentity(
            port=f"SIM{idx}",
            uid=f"SIM-UID-{idx:03d}",
            variant="SIMU",
            version="1.0.0",
            board="SIMBOARD",
        )
        sources.append(SimulatedSource(identity))
    return sources

