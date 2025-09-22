"""Utilities for MSP meter payload validation."""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Tuple


def _split(payload: bytes) -> Tuple[int, bytes]:
    if not payload:
        return 0, payload
    count = payload[0]
    return count, payload[1:]


def parse_meter_payload(payload: bytes, meter_type: str) -> Tuple[Dict[str, Any], str, bool]:
    raw = payload.hex()
    if not payload:
        return ({"meters": [], "count_declared": 0, "invalid": False}, raw, False)
    count, rest = _split(payload)
    entries: List[Dict[str, Any]] = []
    invalid = False
    cursor = 0
    while cursor < len(rest):
        remaining = len(rest) - cursor
        if remaining in (2, 4):
            values = struct.unpack_from("<" + {2: "H", 4: "I"}[remaining], rest, cursor)
            invalid = True
            entries.append({
                "id": len(entries),
                "value_raw": values[0],
                "unit": "auto",
            })
            cursor = len(rest)
            break
        if remaining < 3:
            invalid = True
            break
        meter_id = rest[cursor]
        if remaining >= 3:
            value = rest[cursor + 1] | (rest[cursor + 2] << 8)
            cursor += 3
            entry: Dict[str, Any] = {
                "id": meter_id,
                "value_raw": value,
                "unit": "V(0.1)" if meter_type == "voltage" else "A(0.01)",
            }
            if meter_type == "voltage":
                entry["voltage_V"] = value / 10.0
            elif meter_type == "current":
                entry["amps_A"] = value / 100.0
            entries.append(entry)
        else:
            invalid = True
            break
    if count and count != len(entries):
        invalid = True
    data = {
        "invalid": invalid,
        "count_declared": count,
        "meters": entries,
    }
    return data, raw, invalid
