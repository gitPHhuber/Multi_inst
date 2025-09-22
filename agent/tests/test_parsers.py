import pathlib

from multi_inst_agent.core import parsers

FIXTURES = pathlib.Path(__file__).parent / "payloads"


def load_hex(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text().strip())


def test_status_parsing():
    payload = load_hex("status.hex")
    result = parsers.parse_status(payload)
    assert not result.invalid
    assert result.data["cycleTime_us"] == 250
    assert result.data["i2c_errors"] == 0


def test_attitude_units():
    payload = load_hex("attitude.hex")
    result = parsers.parse_attitude(payload)
    assert result.data["roll_deg"] == -0.3
    assert result.data["pitch_deg"] == 0.8
    assert result.data["yaw_deg"] == 120


def test_altitude_units():
    payload = load_hex("altitude.hex")
    result = parsers.parse_altitude(payload)
    assert result.data["alt_m"] == 2.0
    assert result.data["vario_cmps"] == 5


def test_analog_units():
    payload = load_hex("analog.hex")
    result = parsers.parse_analog(payload)
    assert result.data["vbat_V"] == 12.3
    assert result.data["amps_A"] == 2.5


def test_voltage_meters_valid():
    payload = load_hex("voltage_ok.hex")
    result = parsers.parse_voltage_meters(payload)
    assert not result.invalid
    assert result.data["meters"][0]["voltage_V"] == 5.0


def test_voltage_meters_invalid():
    payload = load_hex("voltage_invalid.hex")
    result = parsers.parse_voltage_meters(payload)
    assert result.invalid


def test_current_meters_valid():
    payload = load_hex("current_ok.hex")
    result = parsers.parse_current_meters(payload)
    assert not result.invalid
    assert result.data["meters"][0]["amps_A"] == 2.0


def test_battery_state():
    payload = load_hex("battery.hex")
    result = parsers.parse_battery_state(payload)
    assert not result.invalid
    assert result.data["voltage_V"] == 16.8
    assert result.data["amps_A"] == 2.5
