"""Pydantic models for FastAPI endpoints."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    ports: List[str] = Field(default_factory=list)
    baud: int = 1_000_000
    profile: str = "usb_stand"
    rates: Dict[str, float] = Field(default_factory=dict)
    record_path: Optional[str] = None
    simulate: bool = False


class StartResponse(BaseModel):
    session_id: str


class StopRequest(BaseModel):
    session_id: str


class StopResponse(BaseModel):
    ok: bool


class InfoResponse(BaseModel):
    version: str
    os: str
    ports: List[Dict[str, str]]


class PortsResponse(BaseModel):
    ports: List[Dict[str, str]]


class SnapshotResponse(BaseModel):
    session_id: str
    devices: List[Dict]
