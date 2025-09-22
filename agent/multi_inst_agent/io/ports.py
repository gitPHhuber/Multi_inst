"""Serial port discovery utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

import serial.tools.list_ports


WHITELIST_DEFAULT_VID: set[int] = {0x0483}
WHITELIST_DEFAULT_PID: set[int] = {0x5740}


@dataclass
class PortFilterConfig:
    """Configuration used when filtering serial ports."""

    enforce_whitelist: bool = True
    whitelist_vid: set[int] = field(default_factory=lambda: set(WHITELIST_DEFAULT_VID))
    whitelist_pid: set[int] = field(default_factory=lambda: set(WHITELIST_DEFAULT_PID))
    allowed_prefixes: Sequence[str] = ("/dev/ttyACM", "/dev/ttyUSB")
    include_simulated: bool = False

    def allow(self, vid: int | None, pid: int | None) -> bool:
        if not self.enforce_whitelist:
            return True
        if vid is None or pid is None:
            # Missing VID/PID information is treated as unknown and rejected when
            # the whitelist is enforced.
            return False
        return vid in self.whitelist_vid and pid in self.whitelist_pid


@dataclass
class PortDescriptor:

    """Metadata describing an available serial interface."""

    device: str
    description: str
    hwid: str
    vid: int | None = None
    pid: int | None = None
    manufacturer: str | None = None
    product: str | None = None
    serial_number: str | None = None
    whitelisted: bool = False
    simulated: bool = False
    reason: str | None = None


def _is_candidate(device: str, prefixes: Sequence[str]) -> bool:
    return any(device.startswith(prefix) for prefix in prefixes)


def _iter_ports(
    include_simulated: bool,
) -> Iterable[serial.tools.list_ports.ListPortInfo]:
    for port in serial.tools.list_ports.comports():
        if not port.device:
            continue
        if include_simulated and port.device.startswith("sim://"):
            yield port
            continue
        yield port


def list_ports(config: PortFilterConfig | None = None) -> List[PortDescriptor]:
    """Discover available serial ports filtered according to *config*."""

    config = config or PortFilterConfig()
    ports: List[PortDescriptor] = []

    for entry in _iter_ports(config.include_simulated):
        device = entry.device or ""
        if not _is_candidate(device, config.allowed_prefixes) and not (
            config.include_simulated and device.startswith("sim://")
        ):
            # Skip system serial ports such as /dev/ttyS*
            continue
        allowed = config.allow(entry.vid, entry.pid)
        if not allowed and not (
            config.include_simulated and device.startswith("sim://")
        ):
            reason = "not whitelisted"
        else:
            reason = None
        if not allowed and reason:
            # Ignore ports that do not pass the whitelist when it is enforced.
            continue
        ports.append(

            PortDescriptor(

                device=device,
                description=entry.description or "",
                hwid=entry.hwid or "",
                vid=getattr(entry, "vid", None),
                pid=getattr(entry, "pid", None),
                manufacturer=getattr(entry, "manufacturer", None),
                product=getattr(entry, "product", None),
                serial_number=getattr(entry, "serial_number", None),
                whitelisted=allowed,
                simulated=device.startswith("sim://"),
                reason=reason,
            )
        )
    ports.sort(key=lambda p: p.device)
    return ports


def list_port_strings(config: PortFilterConfig | None = None) -> List[str]:
    return [p.device for p in list_ports(config)]
