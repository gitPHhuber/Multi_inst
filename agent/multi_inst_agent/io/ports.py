"""Serial port discovery utilities."""

from __future__ import annotations

import glob
from dataclasses import dataclass
from typing import List

import serial.tools.list_ports


@dataclass
class PortInfo:
    device: str
    description: str
    hwid: str
    busy: bool = False


SERIAL_PATTERNS = ("/dev/ttyACM*", "/dev/ttyUSB*")


def list_ports() -> List[PortInfo]:
    ports = []
    for port in serial.tools.list_ports.comports():
        ports.append(
            PortInfo(
                device=port.device,
                description=port.description or "",
                hwid=port.hwid or "",
            )
        )
    if not ports:
        for pattern in SERIAL_PATTERNS:
            for path in glob.glob(pattern):
                ports.append(PortInfo(device=path, description="", hwid=""))
    return ports


def list_port_strings() -> List[str]:
    return [p.device for p in list_ports()]
