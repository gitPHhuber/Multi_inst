"""Collection of MSP payload parsers used by diagnostics."""

from __future__ import annotations

from typing import Dict, List

from .msp import hexlify, le_i16, le_i32, le_u16, le_u32


def parse_status(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data)}
    if len(data) >= 2:
        out["cycleTime_us"] = le_u16(data[0:2])
    if len(data) >= 4:
        out["i2c_errors"] = le_u16(data[2:4])
    if len(data) >= 6:
        mask = le_u16(data[4:6])
        out["sensors_mask"] = mask
        out["sensors"] = _decode_sensors(mask)
    if len(data) >= 10:
        out["flags"] = le_u32(data[6:10])
    return out


def _decode_sensors(mask: int) -> List[str]:
    mapping = [
        (0, "ACC"),
        (1, "BARO"),
        (2, "MAG"),
        (3, "GPS"),
        (4, "SONAR/RANGE"),
    ]
    return [name for bit, name in mapping if mask & (1 << bit)]


def parse_status_ex(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data)}
    if not data:
        return out
    out["payload_len"] = len(data)
    return out


def parse_attitude(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data)}
    if len(data) >= 2:
        out["roll_deg"] = round(le_i16(data[0:2]) / 10.0, 1)
    if len(data) >= 4:
        out["pitch_deg"] = round(le_i16(data[2:4]) / 10.0, 1)
    if len(data) >= 6:
        out["yaw_deg"] = float(le_i16(data[4:6]))
    return out


def parse_altitude(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data)}
    if len(data) >= 4:
        out["alt_m"] = round(le_i32(data[0:4]) / 100.0, 2)
    if len(data) >= 6:
        out["vario_cmps"] = le_i16(data[4:6])
    if len(data) >= 10:
        out["baro_alt_m"] = round(le_i32(data[6:10]) / 100.0, 2)
    return out


def parse_analog(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data)}
    if len(data) >= 1:
        out["vbat_V"] = round(data[0] / 10.0, 2)
    if len(data) >= 3:
        out["mAh_used"] = le_u16(data[1:3])
    if len(data) >= 5:
        out["rssi_raw"] = le_u16(data[3:5])
    if len(data) >= 7:
        out["amps_A"] = round(le_i16(data[5:7]) / 100.0, 3)
    return out


def parse_rc(data: bytes) -> Dict[str, object]:
    channels = [le_u16(data[i : i + 2]) for i in range(0, len(data), 2) if i + 2 <= len(data)]
    out: Dict[str, object] = {"channels": channels, "count": len(channels), "raw": hexlify(data)}
    if channels:
        out["min"] = min(channels)
        out["max"] = max(channels)
    else:
        out["invalid"] = True
    return out


def parse_motors(data: bytes) -> Dict[str, object]:
    motors = [le_u16(data[i : i + 2]) for i in range(0, len(data), 2) if i + 2 <= len(data)]
    out: Dict[str, object] = {"motors": motors, "raw": hexlify(data)}
    if len(motors) * 2 != len(data):
        out["invalid"] = True
    return out


def parse_voltage_meters(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data), "meters": [], "invalid": False}
    if not data:
        out["count_declared"] = 0
        return out
    count = data[0]
    payload = data[1:]
    meters: List[Dict[str, object]] = []
    format_used: str | None = None
    if len(payload) == count * 3:
        format_used = "id+u16"
        for idx in range(count):
            base = idx * 3
            meter_id = payload[base]
            value_raw = le_u16(payload[base + 1 : base + 3])
            scale = 10.0 if value_raw <= 255 else 100.0
            meters.append(
                {
                    "id": meter_id,
                    "value_raw": value_raw,
                    "voltage_V": round(value_raw / scale, 3),
                    "unit": "V(0.1)" if scale == 10.0 else "V(0.01)",
                }
            )
    elif len(payload) == count * 5:
        format_used = "id+i32"
        for idx in range(count):
            base = idx * 5
            meter_id = payload[base]
            value_raw = le_i32(payload[base + 1 : base + 5])
            meters.append(
                {
                    "id": meter_id,
                    "value_raw": value_raw,
                    "voltage_V": round(value_raw / 1000.0, 3),
                    "unit": "V(1mV)",
                }
            )
    elif len(payload) == count * 2:
        format_used = "values"
        for idx in range(count):
            value_raw = le_u16(payload[idx * 2 : idx * 2 + 2])
            scale = 10.0 if value_raw <= 255 else 100.0
            meters.append(
                {
                    "id": idx,
                    "value_raw": value_raw,
                    "voltage_V": round(value_raw / scale, 3),
                    "unit": "V(0.1)" if scale == 10.0 else "V(0.01)",
                }
            )
    else:
        out["invalid"] = True

    out["count_declared"] = count
    if format_used:
        out["format"] = format_used
    if len(meters) != count:
        out["invalid"] = True
    out["meters"] = meters
    return out


def parse_current_meters(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data), "meters": [], "invalid": False}
    if not data:
        out["count_declared"] = 0
        return out
    count = data[0]
    payload = data[1:]
    meters: List[Dict[str, object]] = []
    format_used: str | None = None
    if len(payload) == count * 3:
        format_used = "id+i16"
        for idx in range(count):
            base = idx * 3
            meter_id = payload[base]
            raw = le_i16(payload[base + 1 : base + 3])
            meters.append(
                {
                    "id": meter_id,
                    "value_raw": raw,
                    "amps_A": round(raw / 100.0, 3),
                    "unit": "A(0.01)",
                }
            )
    elif len(payload) == count * 5:
        format_used = "id+i32"
        for idx in range(count):
            base = idx * 5
            meter_id = payload[base]
            raw = le_i32(payload[base + 1 : base + 5])
            meters.append(
                {
                    "id": meter_id,
                    "value_raw": raw,
                    "amps_A": round(raw / 1000.0, 3),
                    "unit": "A(1mA)",
                }
            )
    elif len(payload) == count * 2:
        format_used = "values"
        for idx in range(count):
            raw = le_i16(payload[idx * 2 : idx * 2 + 2])
            meters.append(
                {
                    "id": idx,
                    "value_raw": raw,
                    "amps_A": round(raw / 100.0, 3),
                    "unit": "A(0.01)",
                }
            )
    else:
        out["invalid"] = True

    out["count_declared"] = count
    if format_used:
        out["format"] = format_used
    if len(meters) != count:
        out["invalid"] = True
    out["meters"] = meters
    return out


def parse_battery_state(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data)}
    if len(data) >= 7:
        connected = bool(data[0])
        voltage = le_u16(data[1:3]) / 100.0
        mAh_used = le_u32(data[3:7])
        out.update(
            {
                "connected": connected,
                "voltage_V": round(voltage, 3),
                "mAh_used": mAh_used,
            }
        )
        if len(data) >= 9:
            out["amps_A"] = round(le_i16(data[7:9]) / 100.0, 3)
    else:
        out["invalid"] = True
    return out


__all__ = [
    "parse_altitude",
    "parse_analog",
    "parse_attitude",
    "parse_battery_state",
    "parse_current_meters",
    "parse_motors",
    "parse_rc",
    "parse_status",
    "parse_status_ex",
    "parse_voltage_meters",
]
