"""Parsers for MSP payloads."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Dict

from .meters import parse_meter_payload


@dataclass
class MSPParseResult:
    data: Dict[str, Any]
    raw_hex: str
    invalid: bool = False


MSP_COMMANDS = {
    "MSP_API_VERSION": 1,
    "MSP_FC_VARIANT": 2,
    "MSP_FC_VERSION": 3,
    "MSP_BOARD_INFO": 4,
    "MSP_BUILD_INFO": 5,
    "MSP_NAME": 10,
    "MSP_UID": 160,
    "MSP_STATUS": 101,
    "MSP_STATUS_EX": 150,
    "MSP_RAW_IMU": 102,
    "MSP_ATTITUDE": 108,
    "MSP_ALTITUDE": 109,
    "MSP_ANALOG": 110,
    "MSP_RC": 105,
    "MSP_MOTOR": 104,
    "MSP_VOLTAGE_METERS": 128,
    "MSP_CURRENT_METERS": 129,
    "MSP_BATTERY_STATE": 130,
    "MSP_DATAFLASH_SUMMARY": 70,
    "MSP_ESC_SENSOR_DATA": 134,
}


def _payload_hex(payload: bytes) -> str:
    return payload.hex()


def parse_api_version(payload: bytes) -> MSPParseResult:
    if len(payload) < 3:
        return MSPParseResult({"version": "0.0.0"}, _payload_hex(payload), True)
    major, minor, patch = payload[:3]
    return MSPParseResult({"version": f"{major}.{minor}.{patch}"}, _payload_hex(payload))


def parse_ascii(payload: bytes) -> MSPParseResult:
    try:
        value = payload.rstrip(b"\x00").decode("ascii", errors="ignore")
    except UnicodeDecodeError:
        return MSPParseResult({"value": ""}, _payload_hex(payload), True)
    return MSPParseResult({"value": value}, _payload_hex(payload))


def parse_status(payload: bytes) -> MSPParseResult:
    invalid = len(payload) < 11
    raw = _payload_hex(payload)
    if invalid:
        return MSPParseResult({}, raw, True)
    fields = struct.unpack_from("<HHHHIBB", payload, 0)
    data = {
        "cycleTime_us": fields[0],
        "i2c_errors": fields[1],
        "sensors": fields[2],
        "flags": fields[3],
        "current_profile": fields[4],
        "box_mode_flags": fields[5],
        "pid_profile": fields[6],
    }
    return MSPParseResult(data, raw, False)


def parse_status_ex(payload: bytes) -> MSPParseResult:
    raw = _payload_hex(payload)
    expected_len = 11
    invalid = len(payload) != expected_len
    data = {"raw": raw}
    return MSPParseResult(data, raw, invalid)


def parse_attitude(payload: bytes) -> MSPParseResult:
    if len(payload) < 6:
        return MSPParseResult({}, _payload_hex(payload), True)
    roll, pitch, yaw = struct.unpack_from("<hhh", payload, 0)
    return MSPParseResult(
        {
            "roll_deg": roll / 10.0,
            "pitch_deg": pitch / 10.0,
            "yaw_deg": yaw,
        },
        _payload_hex(payload),
        False,
    )


def parse_altitude(payload: bytes) -> MSPParseResult:
    if len(payload) < 8:
        return MSPParseResult({}, _payload_hex(payload), True)
    alt_cm, vario_cms = struct.unpack_from("<ii", payload, 0)
    return MSPParseResult(
        {
            "alt_m": alt_cm / 100.0,
            "vario_cmps": vario_cms,
        },
        _payload_hex(payload),
        False,
    )


def parse_raw_imu(payload: bytes) -> MSPParseResult:
    if len(payload) < 18:
        return MSPParseResult({}, _payload_hex(payload), True)
    values = struct.unpack_from("<hhhhhhhhh", payload, 0)
    acc = values[:3]
    gyro = values[3:6]
    mag = values[6:9]
    data = {
        "acc_raw": acc,
        "gyro_raw": gyro,
        "mag_raw": mag,
    }
    return MSPParseResult(data, _payload_hex(payload), False)


def parse_analog(payload: bytes) -> MSPParseResult:
    if len(payload) < 7:
        return MSPParseResult({}, _payload_hex(payload), True)
    vbat, power_meter_sum, rssi, amperage, mAh_drawn = struct.unpack_from("<HBHHH", payload, 0)
    data = {
        "vbat_V": vbat / 10.0,
        "mAh_used": mAh_drawn,
        "rssi_raw": rssi,
        "amps_A": amperage / 100.0,
        "power_meter_sum": power_meter_sum,
    }
    return MSPParseResult(data, _payload_hex(payload), False)


def parse_rc(payload: bytes) -> MSPParseResult:
    if len(payload) < 32:
        return MSPParseResult({}, _payload_hex(payload), True)
    channels = list(struct.unpack_from("<16H", payload, 0))
    return MSPParseResult(
        {
            "channels": channels,
            "min": min(channels),
            "max": max(channels),
        },
        _payload_hex(payload),
        False,
    )


def parse_motor(payload: bytes) -> MSPParseResult:
    motor_count = len(payload) // 2
    motors = list(struct.unpack_from(f"<{motor_count}H", payload, 0)) if motor_count else []
    return MSPParseResult({"motors": motors}, _payload_hex(payload), False)


def parse_voltage_meters(payload: bytes) -> MSPParseResult:
    return MSPParseResult(*parse_meter_payload(payload, "voltage"))


def parse_current_meters(payload: bytes) -> MSPParseResult:
    return MSPParseResult(*parse_meter_payload(payload, "current"))


def parse_battery_state(payload: bytes) -> MSPParseResult:
    raw = _payload_hex(payload)
    invalid = len(payload) < 10
    if invalid:
        return MSPParseResult({}, raw, True)
    voltage, mAh, amperage, flags = struct.unpack_from("<IHHH", payload, 0)
    return MSPParseResult(
        {
            "voltage_V": voltage / 100.0,
            "mAh_used": mAh,
            "amps_A": amperage / 100.0,
            "connected": bool(flags & 0x01),
            "flags": flags,
        },
        raw,
        False,
    )


def parse_uid(payload: bytes) -> MSPParseResult:
    if len(payload) < 12:
        return MSPParseResult({}, _payload_hex(payload), True)
    uid = struct.unpack_from("<III", payload, 0)
    return MSPParseResult({"uid": "".join(f"{part:08X}" for part in uid)}, _payload_hex(payload), False)


PARSERS = {
    MSP_COMMANDS["MSP_API_VERSION"]: parse_api_version,
    MSP_COMMANDS["MSP_FC_VARIANT"]: parse_ascii,
    MSP_COMMANDS["MSP_FC_VERSION"]: parse_ascii,
    MSP_COMMANDS["MSP_BOARD_INFO"]: parse_ascii,
    MSP_COMMANDS["MSP_BUILD_INFO"]: parse_ascii,
    MSP_COMMANDS["MSP_NAME"]: parse_ascii,
    MSP_COMMANDS["MSP_UID"]: parse_uid,
    MSP_COMMANDS["MSP_STATUS"]: parse_status,
    MSP_COMMANDS["MSP_STATUS_EX"]: parse_status_ex,
    MSP_COMMANDS["MSP_ATTITUDE"]: parse_attitude,
    MSP_COMMANDS["MSP_ALTITUDE"]: parse_altitude,
    MSP_COMMANDS["MSP_RAW_IMU"]: parse_raw_imu,
    MSP_COMMANDS["MSP_ANALOG"]: parse_analog,
    MSP_COMMANDS["MSP_RC"]: parse_rc,
    MSP_COMMANDS["MSP_MOTOR"]: parse_motor,
    MSP_COMMANDS["MSP_VOLTAGE_METERS"]: parse_voltage_meters,
    MSP_COMMANDS["MSP_CURRENT_METERS"]: parse_current_meters,
    MSP_COMMANDS["MSP_BATTERY_STATE"]: parse_battery_state,
    MSP_COMMANDS["MSP_DATAFLASH_SUMMARY"]: lambda payload: MSPParseResult({"raw": payload.hex()}, payload.hex(), False),
    MSP_COMMANDS["MSP_ESC_SENSOR_DATA"]: lambda payload: MSPParseResult({"raw": payload.hex()}, payload.hex(), False),
}


def parse_payload(cmd: int, payload: bytes) -> MSPParseResult:
    parser = PARSERS.get(cmd)
    if not parser:
        return MSPParseResult({"raw": payload.hex()}, payload.hex(), False)
    result = parser(payload)
    return result
