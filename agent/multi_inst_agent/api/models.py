"""Pydantic models for FastAPI endpoints."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PortInfo(BaseModel):
    device: str
    name: Optional[str] = None
    description: Optional[str] = None
    vid: Optional[str] = None
    pid: Optional[str] = None
    whitelisted: bool = False
    simulated: bool = False
    reason: Optional[str] = None


class StartRequest(BaseModel):
    ports: List[str] = Field(default_factory=list)
    baud: int = 1_000_000
    profile: str = "usb_stand"
    mode: str = Field("normal", pattern="^(normal|pro)$")
    auto: bool = True
    rates: Dict[str, float] = Field(default_factory=dict)
    record_path: Optional[str] = None
    simulate: bool = False
    out_dir: str = "./out"
    enforce_whitelist: bool = True
    include_simulator: bool = False
    duration: float = 5.0


class StartResponse(BaseModel):
    session_id: str


class StopRequest(BaseModel):
    session_id: str


class StopResponse(BaseModel):
    ok: bool


class InfoResponse(BaseModel):
    version: str
    os: str
    ports: List[PortInfo]


class PortsResponse(BaseModel):
    ports: List[PortInfo]


class SnapshotResponse(BaseModel):
    session_id: str
    devices: List[Dict]
