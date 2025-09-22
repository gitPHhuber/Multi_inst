"""Minimal MSP v1 transport helpers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Protocol

import serial

log = logging.getLogger(__name__)

MSP_HEADER = b"$M"
DIR_TO_FC = ord("<")
DIR_FROM_FC = ord(">")


class SerialLike(Protocol):
    baudrate: int

    def write(self, data: bytes) -> int: ...

    def read(self, size: int = 1) -> bytes: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


@dataclass
class MSPFrame:
    cmd: int
    payload: bytes
    direction: int
    checksum: int

    def to_dict(self) -> dict:
        return {
            "cmd": self.cmd,
            "payload_hex": self.payload.hex(),
            "direction": self.direction,
            "checksum": self.checksum,
        }


def build_frame_v1(cmd: int, payload: bytes = b"") -> bytes:
    if not (0 <= cmd < 256):
        raise ValueError("command must fit in a single byte")
    if len(payload) > 255:
        raise ValueError("payload too large for MSP v1")
    checksum = 0
    frame = bytearray()
    frame.extend(MSP_HEADER)
    frame.append(DIR_TO_FC)
    frame.append(len(payload))
    frame.append(cmd)
    checksum ^= len(payload)
    checksum ^= cmd
    for b in payload:
        checksum ^= b
    frame.extend(payload)
    frame.append(checksum)
    return bytes(frame)


def _read_exact(ser: SerialLike, size: int, timeout: float) -> bytes:
    deadline = time.time() + timeout
    chunks = bytearray()
    while len(chunks) < size and time.time() < deadline:
        chunk = ser.read(size - len(chunks))
        if chunk:
            chunks.extend(chunk)
        else:
            time.sleep(0.001)
    return bytes(chunks)


def read_response_v1(ser: SerialLike, expect_cmd: Optional[int], timeout: float) -> tuple[Optional[int], bytes, Optional[str]]:
    deadline = time.time() + timeout
    buffer = bytearray()
    while time.time() < deadline:
        chunk = ser.read(1)
        if not chunk:
            time.sleep(0.001)
            continue
        buffer.extend(chunk)
        if len(buffer) >= 3 and buffer[-3:-1] == MSP_HEADER:
            direction = buffer[-1]
            if direction != DIR_FROM_FC:
                continue
            length_bytes = _read_exact(ser, 1, timeout)
            if len(length_bytes) != 1:
                return None, b"", "timeout waiting length"
            payload_len = length_bytes[0]
            cmd_bytes = _read_exact(ser, 1, timeout)
            if len(cmd_bytes) != 1:
                return None, b"", "timeout waiting command"
            cmd = cmd_bytes[0]
            payload = _read_exact(ser, payload_len, timeout)
            if len(payload) != payload_len:
                return None, payload, "timeout waiting payload"
            checksum_bytes = _read_exact(ser, 1, timeout)
            if len(checksum_bytes) != 1:
                return None, payload, "timeout waiting checksum"
            checksum = checksum_bytes[0]
            computed = payload_len ^ cmd
            for b in payload:
                computed ^= b
            if checksum != computed:
                return cmd, payload, "checksum"
            if expect_cmd is not None and cmd != expect_cmd:
                return cmd, payload, "unexpected_cmd"
            return cmd, payload, None
    return None, b"", "timeout"


def open_serial_port(port: str, baudrate: int = 1_000_000, timeout: float = 0.1) -> serial.Serial:
    ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.05)
    ser.dtr = True
    ser.rts = True
    return ser


def send_command(ser: serial.Serial, cmd: int, payload: bytes = b"", timeout: float = 0.3, retries: int = 3) -> tuple[Optional[int], bytes, Optional[str]]:
    frame = build_frame_v1(cmd, payload)
    for attempt in range(1, retries + 1):
        ser.write(frame)
        ser.flush()
        cmd_resp, payload_resp, error = read_response_v1(ser, cmd, timeout)
        if error is None:
            return cmd_resp, payload_resp, None
        log.debug("MSP command %s failed attempt %s/%s: %s", cmd, attempt, retries, error)
        time.sleep(0.02 * attempt)
    return None, b"", error or "timeout"
