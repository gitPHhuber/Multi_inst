"""FastAPI application for the Multi Inst agent."""

from __future__ import annotations

import asyncio
import platform
import random
import time
import uuid
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from .. import __version__
from ..io.ports import list_ports, list_port_strings
from .models import (
    InfoResponse,
    PortsResponse,
    SnapshotResponse,
    StartRequest,
    StartResponse,
    StopRequest,
    StopResponse,
)

app = FastAPI(title="Multi Inst Agent", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimulatedDevice:
    def __init__(self, port: str, profile: str) -> None:
        self.port = port
        self.profile = profile
        self.uid = f"SIM-{port.split('/')[-1]}"
        self.counter = 0
        self.start_time = time.time()

    def step(self) -> Dict[str, Any]:
        self.counter += 1
        ts = time.time()
        cycle = 250.0 + random.random() * 5
        gyro = (
            random.gauss(0, 2),
            random.gauss(0, 2),
            random.gauss(0, 2),
        )
        imu_stats = {
            "samples": self.counter,
            "gyro_std": [abs(g) for g in gyro],
            "gyro_bias": [g / 2 for g in gyro],
            "acc_norm_std": random.random() * 3,
        }
        loop_stats = {
            "samples": self.counter,
            "cycle_us_mean": cycle,
            "cycle_us_std": random.random() * 2,
            "cycle_us_min": cycle - 2,
            "cycle_us_max": cycle + 2,
            "p95": cycle + 3,
            "p99": cycle + 4,
            "loop_hz_mean": 1_000_000.0 / cycle,
        }
        analog = {
            "vbat_V": max(0.0, 16.5 - self.counter * 0.0005),
            "amps_A": abs(random.gauss(0, 3)),
            "mAh_used": int(self.counter * 0.1),
            "rssi_raw": 1000,
            "raw": "",
        }
        return {
            "uid": self.uid,
            "port": self.port,
            "baud": 1_000_000,
            "ok": True,
            "reasons": [],
            "meta": {
                "fc_variant": "BTFL",
                "fc_version": "4.5.0",
                "board_id": "SIM",
                "api_version": "0.1.0",
                "build_info": "simulated",
            },
            "status": {
                "cycleTime_us": 250,
                "i2c_errors": 0,
                "sensors_mask": 0,
                "raw": "",
            },
            "attitude": {
                "roll_deg": random.gauss(0, 0.5),
                "pitch_deg": random.gauss(0, 0.5),
                "yaw_deg": random.random() * 360,
            },
            "altitude": {
                "alt_m": random.gauss(0, 0.05),
                "vario_cmps": random.gauss(0, 1),
                "raw": "",
            },
            "analog": analog,
            "rc": {
                "channels": [1500 for _ in range(16)],
                "min": 1500,
                "max": 1500,
            },
            "motors": {
                "motors": [1000 for _ in range(8)],
            },
            "voltage_meters": {
                "invalid": False,
                "count_declared": 1,
                "meters": [
                    {
                        "id": 0,
                        "value_raw": int(analog["vbat_V"] * 10),
                        "voltage_V": analog["vbat_V"],
                        "unit": "V(0.1)",
                    }
                ],
                "raw": "",
            },
            "current_meters": {
                "invalid": False,
                "count_declared": 1,
                "meters": [
                    {
                        "id": 0,
                        "value_raw": int(analog["amps_A"] * 100),
                        "amps_A": analog["amps_A"],
                        "unit": "A(0.01)",
                    }
                ],
                "raw": "",
            },
            "battery_state": {
                "connected": analog["vbat_V"] > 0,
                "voltage_V": analog["vbat_V"],
                "mAh_used": analog["mAh_used"],
                "amps_A": analog["amps_A"],
                "raw": "",
            },
            "imu_stats": imu_stats,
            "loop_stats": loop_stats,
            "raw_seen": {"101": self.counter, "108": self.counter * 2},
            "duration_s": ts - self.start_time,
        }


class Session:
    def __init__(
        self, session_id: str, ports: List[str], baud: int, profile: str, simulate: bool
    ) -> None:
        self.id = session_id
        self.ports = ports
        self.baud = baud
        self.profile = profile
        self.simulate = simulate
        self.created = time.time()
        self.running = True
        self.devices: Dict[str, SimulatedDevice] = {}
        self.snapshots: Dict[str, Dict[str, Any]] = {}
        self.queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self.task = asyncio.create_task(self._run())
        for port in ports:
            device = SimulatedDevice(port, profile)
            self.devices[device.uid] = device

    async def _run(self) -> None:
        while self.running:
            for uid, device in list(self.devices.items()):
                snapshot = device.step()
                self.snapshots[uid] = snapshot
                event = {"type": "snapshot", "uid": uid, "data": snapshot}
                await self._publish(event)
            await asyncio.sleep(0.1)

    async def _publish(self, event: Dict[str, Any]) -> None:
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self.queue.put(event)

    async def get_events(self):
        while self.running:
            event = await self.queue.get()
            yield event

    def snapshot(self) -> List[Dict[str, Any]]:
        return list(self.snapshots.values())

    async def stop(self) -> None:
        self.running = False
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass


class SessionManager:
    def __init__(self) -> None:
        self.sessions: Dict[str, Session] = {}
        self.reports: Dict[str, Dict] = {}

    def start_session(
        self, ports: List[str], baud: int, profile: str, simulate: bool
    ) -> Session:
        session_id = uuid.uuid4().hex
        if not ports:
            ports = list_port_strings()
        if not ports:
            ports = ["/dev/ttyACM0"]
        session = Session(session_id, ports, baud, profile, simulate)
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


manager = SessionManager()


@app.get("/v1/info", response_model=InfoResponse)
def get_info() -> InfoResponse:
    ports = [port.__dict__ for port in list_ports()]
    return InfoResponse(version=__version__, os=platform.platform(), ports=ports)


@app.get("/v1/ports", response_model=PortsResponse)
def get_ports() -> PortsResponse:
    ports = [port.__dict__ for port in list_ports()]
    return PortsResponse(ports=ports)


@app.post("/v1/start", response_model=StartResponse)
async def start_session(req: StartRequest) -> StartResponse:
    session = manager.start_session(req.ports, req.baud, req.profile, req.simulate)
    return StartResponse(session_id=session.id)


@app.post("/v1/stop", response_model=StopResponse)
async def stop_session(req: StopRequest) -> StopResponse:
    await manager.stop_session(req.session_id)
    return StopResponse(ok=True)


@app.get("/v1/snapshot", response_model=SnapshotResponse)
async def get_snapshot(session_id: str) -> SnapshotResponse:
    try:
        session = manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")
    return SnapshotResponse(session_id=session_id, devices=session.snapshot())


@app.websocket("/v1/stream")
async def stream(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    try:
        session = manager.get_session(session_id)
    except KeyError:
        await ws.close(code=4004)
        return
    try:
        while True:
            if ws.application_state == WebSocketState.DISCONNECTED:
                break
            try:
                event = await asyncio.wait_for(session.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping", "ts": time.time()})
                continue
            await ws.send_json(event)
    except WebSocketDisconnect:
        return


@app.get("/v1/report/{uid}")
async def get_report(uid: str) -> Dict[str, Any]:
    report = manager.reports.get(uid)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return report
