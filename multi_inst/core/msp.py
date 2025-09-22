"""MSP transport primitives and client implementation."""

from __future__ import annotations

import binascii
import struct
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol

MSP_V1_START = b"$M"
DIR_TO_FC = ord("<")
DIR_FROM_FC = ord(">")


class MSPError(Exception):
    """Base class for MSP related errors."""


class MSPChecksumError(MSPError):
    """Raised when a response fails XOR validation."""


class MSPTimeoutError(MSPError):
    """Raised when a response cannot be read within the timeout."""


class SerialLike(Protocol):
    """Protocol describing the subset of serial.Serial we rely on."""

    timeout: Optional[float]

    def read(self, size: int) -> bytes:  # pragma: no cover - protocol signature
        ...

    def write(self, data: bytes) -> int:  # pragma: no cover - protocol signature
        ...

    def flush(self) -> None:  # pragma: no cover - protocol signature
        ...

    dtr: bool
    rts: bool


@dataclass(frozen=True)
class MSPFrame:
    """Representation of a raw MSP v1 frame."""

    command: int
    payload: bytes

    def to_bytes(self) -> bytes:
        payload_len = len(self.payload)
        checksum = payload_len ^ self.command
        for byte in self.payload:
            checksum ^= byte
        return (
            MSP_V1_START
            + bytes([DIR_TO_FC, payload_len, self.command])
            + self.payload
            + bytes([checksum & 0xFF])
        )


def build_frame(command: int, payload: bytes = b"") -> MSPFrame:
    """Construct an :class:`MSPFrame` for the provided command and payload."""

    if not 0 <= command <= 0xFF:
        raise ValueError("command must fit in uint8")
    if len(payload) > 0xFF:
        raise ValueError("payload cannot exceed 255 bytes in MSP v1")
    return MSPFrame(command=command, payload=bytes(payload))


def _xor_checksum(size: int, command: int, payload: Iterable[int]) -> int:
    checksum = size ^ command
    for byte in payload:
        checksum ^= byte
    return checksum & 0xFF


class MSPClient:
    """Minimal MSP v1 client handling framing, retries and wake-up logic."""

    def __init__(
        self,
        ser: SerialLike,
        *,
        response_timeout: float = 0.3,
        inter_command_gap: float = 0.0,
        retries: int = 1,
    ) -> None:
        self._serial = ser
        self._timeout = response_timeout
        self._gap = inter_command_gap
        self._retries = max(1, retries)

    @staticmethod
    def wake_port(port: SerialLike) -> None:
        """Toggle DTR/RTS lines to wake USB VCP devices."""

        try:
            port.dtr = False
            port.rts = False
            time.sleep(0.05)
            port.dtr = True
            port.rts = True
            time.sleep(0.05)
        except Exception:
            # Not all serial backends expose DTR/RTS (e.g. mocks in tests)
            pass

    def wake(self) -> None:
        """Wake the underlying serial port if supported."""

        self.wake_port(self._serial)

    def request(
        self,
        command: int,
        payload: bytes = b"",
        *,
        timeout: Optional[float] = None,
    ) -> bytes:
        """Send a command and return the raw payload from the FC."""

        frame = build_frame(command, payload)
        for attempt in range(1, self._retries + 1):
            self._serial.write(frame.to_bytes())
            self._serial.flush()
            if self._gap:
                time.sleep(self._gap)
            try:
                return self._read_response(command, timeout=timeout)
            except MSPTimeoutError:
                if attempt >= self._retries:
                    raise
                time.sleep(0.05)
        raise MSPTimeoutError("request exhausted retries without response")

    def _read_response(self, expected_command: int, *, timeout: Optional[float] = None) -> bytes:
        deadline = time.time() + (timeout if timeout is not None else self._timeout)
        serial = self._serial
        while time.time() < deadline:
            head = serial.read(1)
            if not head:
                continue
            if head != b"$":
                continue
            if serial.read(1) != b"M":
                continue
            direction = serial.read(1)
            if direction != bytes([DIR_FROM_FC]):
                continue
            size_bytes = serial.read(1)
            if not size_bytes:
                continue
            size = size_bytes[0]
            command_bytes = serial.read(1)
            if not command_bytes:
                continue
            command = command_bytes[0]
            payload = serial.read(size)
            checksum_bytes = serial.read(1)
            if len(payload) != size or not checksum_bytes:
                raise MSPTimeoutError("truncated frame")
            checksum = checksum_bytes[0]
            calc = _xor_checksum(size, command, payload)
            if checksum != calc:
                raise MSPChecksumError(
                    f"checksum mismatch: expected {calc:02x}, got {checksum:02x}"
                )
            if command != expected_command:
                # Unexpected response - drop and continue waiting.
                continue
            return payload
        raise MSPTimeoutError(f"timeout waiting for MSP command {expected_command}")


def hexlify(data: bytes) -> str:
    """Return a lowercase hexadecimal representation of *data*."""

    return binascii.hexlify(data).decode("ascii")


def le_u16(data: bytes) -> int:
    return struct.unpack("<H", data)[0]


def le_i16(data: bytes) -> int:
    return struct.unpack("<h", data)[0]


def le_u32(data: bytes) -> int:
    return struct.unpack("<I", data)[0]


def le_i32(data: bytes) -> int:
    return struct.unpack("<i", data)[0]
