"""Shared data models for the real-time GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(slots=True)
class DeviceIdentity:
    """Static metadata about a flight controller device."""

    port: str
    uid: str
    variant: str | None = None
    version: str | None = None
    board: str | None = None


@dataclass(slots=True)
class TelemetryFrame:
    """Snapshot of MSP telemetry returned by the polling workers."""

    timestamp: float
    status: Dict[str, object] = field(default_factory=dict)
    attitude: Dict[str, object] = field(default_factory=dict)
    altitude: Dict[str, object] = field(default_factory=dict)
    analog: Dict[str, object] = field(default_factory=dict)
    rc: Dict[str, object] = field(default_factory=dict)
    motors: Dict[str, object] = field(default_factory=dict)
    voltage_meters: List[Dict[str, object]] = field(default_factory=list)
    current_meters: List[Dict[str, object]] = field(default_factory=list)
    battery_state: Dict[str, object] = field(default_factory=dict)
    raw_imu: Dict[str, object] = field(default_factory=dict)
    raw_packets: Dict[str, str] = field(default_factory=dict)

    def value(self, path: str, default: Optional[float] = None) -> Optional[float]:
        """Convenience helper to pull scalar values from nested dictionaries."""

        namespace, _, key = path.partition(".")
        if not namespace or not key:
            return default
        payload = getattr(self, namespace, None)
        if not isinstance(payload, dict):
            return default
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        return default

