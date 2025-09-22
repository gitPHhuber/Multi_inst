from __future__ import annotations

import pytest

from multi_inst.core import parsers


def test_parse_status_includes_raw_and_units():
    payload = bytes([0x10, 0x27, 0x02, 0x00, 0x01, 0x00, 0xAA, 0x55, 0x00, 0x00])
    result = parsers.parse_status(payload)
    assert result["raw"] == payload.hex()
    assert result["cycleTime_us"] == 10000
    assert result["i2c_errors"] == 2
    assert "ACC" in result["sensors"]


def test_parse_attitude_scales_degrees():
    payload = bytes([0x64, 0x00, 0x9C, 0xFF, 0x20, 0x03])
    result = parsers.parse_attitude(payload)
    assert result["raw"] == payload.hex()
    assert result["roll_deg"] == pytest.approx(10.0)
    assert result["pitch_deg"] == pytest.approx(-10.0)
    assert result["yaw_deg"] == 800.0


def test_parse_altitude_converts_to_meters():
    payload = (1000).to_bytes(4, "little", signed=True) + (50).to_bytes(2, "little", signed=True)
    payload += (1500).to_bytes(4, "little", signed=True)
    result = parsers.parse_altitude(payload)
    assert result["raw"] == payload.hex()
    assert result["alt_m"] == 10.0
    assert result["vario_cmps"] == 50
    assert result["baro_alt_m"] == 15.0


def test_parse_analog_units():
    payload = bytes([50, 0x10, 0x00, 0x34, 0x12, 0xF4, 0x01])
    result = parsers.parse_analog(payload)
    assert result["raw"] == payload.hex()
    assert result["vbat_V"] == pytest.approx(5.0)
    assert result["mAh_used"] == 0x0010
    assert result["amps_A"] == pytest.approx(5.0)


def test_parse_voltage_meters_id_u16():
    payload = bytes([2, 1, 200, 0, 2, 0x20, 0x03])
    result = parsers.parse_voltage_meters(payload)
    assert "invalid" not in result
    assert result["count_declared"] == 2
    assert result["meters"][0]["voltage_V"] == pytest.approx(20.0)
    assert result["meters"][1]["voltage_V"] == pytest.approx(8.0)


def test_parse_voltage_meters_values_only():
    payload = bytes([2, 0x10, 0x00, 0x20, 0x03])
    result = parsers.parse_voltage_meters(payload)
    assert result["format"] == "values_only"
    assert result["meters"][0]["voltage_V"] == pytest.approx(1.6)


def test_parse_voltage_meters_invalid_length():
    payload = bytes([1, 0x01])
    result = parsers.parse_voltage_meters(payload)
    assert result["invalid"] is True


def test_parse_current_meters_formats():
    payload_i16 = bytes([1, 5, 0xE8, 0x03])
    result_i16 = parsers.parse_current_meters(payload_i16)
    assert result_i16["format"] == "id_i16"
    assert result_i16["meters"][0]["amps_A"] == pytest.approx(10.0)

    payload_i32 = bytes([1, 5, 0x10, 0x27, 0x00, 0x00])
    result_i32 = parsers.parse_current_meters(payload_i32)
    assert result_i32["format"] == "id_i32"
    assert result_i32["meters"][0]["amps_A"] == pytest.approx(10.0)

    payload_values_only = bytes([2, 0xE8, 0x03, 0xD0, 0x07])
    result_values = parsers.parse_current_meters(payload_values_only)
    assert result_values["format"] == "values_only"
    assert result_values["meters"][1]["amps_A"] == pytest.approx(20.0)


def test_parse_current_meters_invalid():
    payload = bytes([1, 0x01])
    result = parsers.parse_current_meters(payload)
    assert result["invalid"] is True


def test_parse_battery_state_handles_short_payload():
    payload = bytes([0x01, 0x10, 0x27])
    result = parsers.parse_battery_state(payload)
    assert result["raw"] == payload.hex()
    assert result["invalid"] is True
