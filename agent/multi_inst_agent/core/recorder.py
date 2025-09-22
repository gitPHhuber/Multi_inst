"""MSP frame recorder writing zstd compressed logs."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import zstandard as zstd

from .utils import ensure_dir


@dataclass
class RecorderEvent:
    ts: float
    port: str
    direction: str
    cmd: int
    payload: bytes
    checksum: int

    def to_json(self) -> str:
        return json.dumps(
            {
                "ts": self.ts,
                "port": self.port,
                "dir": self.direction,
                "cmd": self.cmd,
                "len": len(self.payload),
                "payload_hex": self.payload.hex(),
                "csum": self.checksum,
            },
            separators=(",", ":"),
        )


class MSPRecorder:
    def __init__(self, path: str) -> None:
        ensure_dir(os.path.dirname(path) or ".")
        self.path = path
        self._fp = open(path, "wb")
        self._compressor = zstd.ZstdCompressor(level=3)
        self._writer = self._compressor.stream_writer(self._fp)

    def record(self, event: RecorderEvent) -> None:
        line = event.to_json().encode("utf-8") + b"\n"
        self._writer.write(line)

    def close(self) -> None:
        self._writer.flush(zstd.FLUSH_FRAME)
        self._writer.close()
        self._fp.close()

    def __enter__(self) -> "MSPRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
