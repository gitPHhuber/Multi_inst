from __future__ import annotations

from types import SimpleNamespace

import pytest

from multi_inst_agent.io.ports import PortFilterConfig, list_port_strings


def _make_port(device: str, vid: int | None = None, pid: int | None = None):
    return SimpleNamespace(
        device=device,
        description=f"Port {device}",
        hwid="USB VID:PID",  # type: ignore[assignment]
        vid=vid,
        pid=pid,
        manufacturer="Vendor",
        product="Product",
        serial_number="1234",
    )


@pytest.fixture(autouse=True)
def reset_list_ports(monkeypatch):
    called = {}

    def fake_comports():
        return called["ports"]

    monkeypatch.setattr("serial.tools.list_ports.comports", fake_comports)
    called["ports"] = []
    return called


def test_filters_out_non_usb_ports(reset_list_ports):
    reset_list_ports["ports"] = [
        _make_port("/dev/ttyS0", vid=0x0483, pid=0x5740),
        _make_port("/dev/ttyACM0", vid=0x0483, pid=0x5740),
    ]
    assert list_port_strings() == ["/dev/ttyACM0"]


def test_requires_whitelisted_vid_pid(reset_list_ports):
    reset_list_ports["ports"] = [
        _make_port("/dev/ttyACM1", vid=0x1111, pid=0x2222),
        _make_port("/dev/ttyUSB0", vid=0x0483, pid=0x5740),
    ]
    assert list_port_strings() == ["/dev/ttyUSB0"]


def test_can_disable_whitelist(reset_list_ports):
    reset_list_ports["ports"] = [
        _make_port("/dev/ttyACM2", vid=None, pid=None),
        _make_port("/dev/ttyUSB1", vid=0x1111, pid=0x2222),
    ]
    config = PortFilterConfig(enforce_whitelist=False)
    ports = list_port_strings(config)
    assert ports == ["/dev/ttyACM2", "/dev/ttyUSB1"]


def test_includes_simulated_when_requested(reset_list_ports):
    reset_list_ports["ports"] = [
        _make_port("sim://001", vid=None, pid=None),
        _make_port("/dev/ttyACM3", vid=0x0483, pid=0x5740),
    ]
    config = PortFilterConfig(include_simulated=True, enforce_whitelist=False)
    ports = list_port_strings(config)
    assert ports == ["/dev/ttyACM3", "sim://001"]
