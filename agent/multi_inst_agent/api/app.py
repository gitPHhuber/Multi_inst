"""FastAPI application for the Multi Inst agent."""

from __future__ import annotations

import platform
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from .. import __version__
from ..core.runtime import SessionManager
from ..io.ports import PortDescriptor, PortFilterConfig, list_ports
from .models import (
    InfoResponse,
    PortInfo,
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

manager = SessionManager()


def _build_port_filter(req: StartRequest) -> PortFilterConfig:
    return PortFilterConfig(
        enforce_whitelist=req.enforce_whitelist,
        include_simulated=req.include_simulator or req.simulate,
    )


def _fmt_hex(value: int | None) -> str | None:
    return f"0x{value:04x}" if value is not None else None


def _as_port_info(descriptor: PortDescriptor) -> PortInfo:
    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    name = _clean(descriptor.manufacturer) or _clean(descriptor.product)
    description = _clean(descriptor.description)
    return PortInfo(
        device=descriptor.device,
        name=name,
        description=description,
        vid=_fmt_hex(descriptor.vid),
        pid=_fmt_hex(descriptor.pid),
        whitelisted=bool(descriptor.whitelisted),
        simulated=bool(descriptor.simulated),
        reason=descriptor.reason,
    )


@app.get("/v1/info", response_model=InfoResponse)
def get_info() -> InfoResponse:
    ports = [_as_port_info(port) for port in list_ports()]
    return InfoResponse(version=__version__, os=platform.platform(), ports=ports)


@app.get("/v1/ports", response_model=PortsResponse)
def get_ports() -> PortsResponse:
    ports = [_as_port_info(port) for port in list_ports()]
    return PortsResponse(ports=ports)


@app.post("/v1/start", response_model=StartResponse)
async def start_session(req: StartRequest) -> StartResponse:
    session = manager.start_session(
        req.ports,
        req.baud,
        req.profile,
        req.mode,
        req.auto,
        req.simulate,
        req.out_dir,
        _build_port_filter(req),
        req.duration,
    )
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
                event = await session.queue.get()
            except Exception:  # pragma: no cover - defensive
                continue
            await ws.send_json(event)
    except WebSocketDisconnect:
        return


@app.post("/v1/retest", response_model=StopResponse)
async def retest_device(session_id: str, uid: str) -> StopResponse:
    try:
        session = manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")
    try:
        await session.retest(uid)
    except KeyError:
        raise HTTPException(status_code=404, detail="device not found")
    return StopResponse(ok=True)


@app.get("/v1/report/{uid}")
async def get_report(uid: str) -> Dict[str, Any]:
    report = manager.reports.get(uid)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return report
