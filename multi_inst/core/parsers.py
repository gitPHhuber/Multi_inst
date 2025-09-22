"""Collection of MSP payload parsers used by diagnostics."""

from __future__ import annotations

from typing import Dict, List

from .msp import hexlify, le_i16, le_i32, le_u16, le_u32


def _voltage_from_raw(value_raw: int) -> Dict[str, object]:
    if value_raw <= 255:
        voltage = round(value_raw / 10.0, 3)
        unit = "V(0.1)"
    else:
        voltage = round(value_raw / 100.0, 3)
        unit = "V(0.01)"
    return {"voltage_V": voltage, "unit": unit}


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


def parse_attitude(data: bytes) -> Dict[str, float]:
    out: Dict[str, float] = {"raw": hexlify(data)}
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
    out: Dict[str, object] = {"raw": hexlify(data), "channels": channels, "count": len(channels)}
    if channels:
        out["min"] = min(channels)
        out["max"] = max(channels)
    return out


def parse_motors(data: bytes) -> Dict[str, object]:
    motors = [le_u16(data[i : i + 2]) for i in range(0, len(data), 2) if i + 2 <= len(data)]
    return {"raw": hexlify(data), "motors": motors}


def parse_voltage_meters(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data), "meters": []}
    if not data:
        out["invalid"] = True
        out["error"] = "missing count"
        return out
    count = data[0]
    payload = data[1:]
    out["count_declared"] = count
    if count == 0:
        if payload:
            out["invalid"] = True
            out["error"] = "unexpected payload for zero count"
        return out
    if len(payload) == count * 3:
        meters = []
        idx = 0
        while idx + 3 <= len(payload):
            meter_id = payload[idx]
            value_raw = le_u16(payload[idx + 1 : idx + 3])
            idx += 3
            entry = {"id": meter_id, "value_raw": value_raw}
            entry.update(_voltage_from_raw(value_raw))
            meters.append(entry)
        out["meters"] = meters
        return out
    if len(payload) == count * 2:
        meters = []
        idx = 0
        while idx + 2 <= len(payload):
            value_raw = le_u16(payload[idx : idx + 2])
            idx += 2
            entry = {"index": len(meters), "value_raw": value_raw}
            entry.update(_voltage_from_raw(value_raw))
            meters.append(entry)
        out["meters"] = meters
        out["format"] = "values_only"
        return out
    out["invalid"] = True
    out["error"] = "payload length mismatch"
    out["payload_len"] = len(data)
    return out


def parse_current_meters(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data), "meters": []}
    if not data:
        out["invalid"] = True
        out["error"] = "missing count"
        return out
    count = data[0]
    payload = data[1:]
    out["count_declared"] = count
    if count == 0:
        if payload:
            out["invalid"] = True
            out["error"] = "unexpected payload for zero count"
        return out
    if len(payload) == count * 3:
        meters = []
        idx = 0
        while idx + 3 <= len(payload):
            meter_id = payload[idx]
            raw = le_i16(payload[idx + 1 : idx + 3])
            idx += 3
            meters.append(
                {
                    "id": meter_id,
                    "value_raw": raw,
                    "amps_A": round(raw / 100.0, 3),
                    "unit": "A(0.01)",
                }
            )
        out["meters"] = meters
        out["format"] = "id_i16"
        return out
    if len(payload) == count * 5:
        meters = []
        idx = 0
        while idx + 5 <= len(payload):
            meter_id = payload[idx]
            raw32 = le_i32(payload[idx + 1 : idx + 5])
            idx += 5
            meters.append(
                {
                    "id": meter_id,
                    "value_raw": raw32,
                    "amps_A": round(raw32 / 1000.0, 3),
                    "unit": "A(1mA)",
                }
            )
        out["meters"] = meters
        out["format"] = "id_i32"
        return out
    if len(payload) == count * 2:
        meters = []
        idx = 0
        while idx + 2 <= len(payload):
            raw = le_i16(payload[idx : idx + 2])
            idx += 2
            meters.append(
                {
                    "index": len(meters),
                    "value_raw": raw,
                    "amps_A": round(raw / 100.0, 3),
                    "unit": "A(0.01)",
                }
            )
        out["meters"] = meters
        out["format"] = "values_only"
        return out
    out["invalid"] = True
    out["error"] = "payload length mismatch"
    out["payload_len"] = len(data)
    return out


def parse_battery_state(data: bytes) -> Dict[str, object]:
    out: Dict[str, object] = {"raw": hexlify(data)}
    if len(data) < 7:
        out["invalid"] = True
        out["error"] = "payload too short"
        return out
    if len(data) not in (7, 9):
        out["invalid"] = True
        out["error"] = "unexpected payload length"
        return out
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
    return out
