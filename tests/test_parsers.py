from pathlib import Path

import pytest

from multi_inst.core import parsers
from multi_inst.core.config import load_profiles, resolve_profile
from multi_inst.core.diagnostics import DiagConfig


def test_parse_status_basic():
    payload = bytes([0xE8, 0x03, 0x00, 0x00, 0x05, 0x00, 0xAA, 0xBB, 0xCC, 0xDD])
    parsed = parsers.parse_status(payload)
    assert parsed["cycleTime_us"] == 1000
    assert parsed["sensors"] == ["ACC", "MAG"]
    assert parsed["raw"] == payload.hex()


def test_parse_attitude_and_altitude_scaling():
    att_payload = b"\xf4\x01\x0a\x00\xd0\xff"
    altitude_payload = le_bytes(1234, 4) + le_bytes(25, 2) + le_bytes(-890, 4)
    att = parsers.parse_attitude(att_payload)
    alt = parsers.parse_altitude(altitude_payload)
    assert att["roll_deg"] == 50.0
    assert att["yaw_deg"] == -48.0
    assert alt["alt_m"] == pytest.approx(12.34)
    assert alt["baro_alt_m"] == pytest.approx(-8.9)


def test_parse_analog_scaling():
    payload = bytes([112, 0x10, 0x27, 0x34, 0x12, 0xF4, 0x01])
    analog = parsers.parse_analog(payload)
    assert analog["vbat_V"] == 11.2
    assert analog["mAh_used"] == 10000
    assert analog["rssi_raw"] == 4660
    assert analog["amps_A"] == pytest.approx(5.0)


def test_parse_voltage_meters_variants():
    payload = bytes([2, 0, 50, 0x00, 1, 0x90, 0x01])
    parsed = parsers.parse_voltage_meters(payload)
    assert not parsed["invalid"]
    assert parsed["meters"][0]["voltage_V"] == 5.0
    assert parsed["meters"][1]["voltage_V"] == pytest.approx(4.0)

    payload_values_only = bytes([1, 0x20, 0x03])
    parsed_values = parsers.parse_voltage_meters(payload_values_only)
    assert parsed_values["format"] == "values"
    assert parsed_values["meters"][0]["voltage_V"] == pytest.approx(80.0 / 10)


def test_parse_voltage_meters_invalid_length():
    payload = bytes([2, 0, 50, 1])
    parsed = parsers.parse_voltage_meters(payload)
    assert parsed["invalid"] is True
    assert parsed["meters"] == []


def test_parse_current_meters_formats():
    payload = bytes([1, 0, 0x64, 0x00])
    parsed = parsers.parse_current_meters(payload)
    assert parsed["meters"][0]["amps_A"] == pytest.approx(1.0)

    payload_i32 = bytes([1, 0, 0xE8, 0x03, 0x00, 0x00])
    parsed_i32 = parsers.parse_current_meters(payload_i32)
    assert parsed_i32["meters"][0]["amps_A"] == pytest.approx(1.0)


def test_battery_state_short_payload_flagged():
    parsed = parsers.parse_battery_state(b"\x01\x00")
    assert parsed.get("invalid") is True


def test_diag_config_profile_overrides(tmp_path: Path):
    profiles = load_profiles()
    profile = resolve_profile("usb_stand", profiles)
    cfg = DiagConfig.from_profile(
        out_dir=tmp_path,
        baud=1_000_000,
        imu_seconds=1.0,
        status_samples=5,
        profile=profile,
        jsonl=False,
    )
    overridden = cfg.with_overrides(max_gyro_std=3.0, ignore_tilt=False)
    assert overridden.max_gyro_std == 3.0
    assert overridden.ignore_tilt is False


def le_bytes(value: int, length: int) -> bytes:
    return int(value).to_bytes(length, byteorder="little", signed=value < 0)
