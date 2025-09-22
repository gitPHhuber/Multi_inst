from __future__ import annotations

import time

from multi_inst.core import msp
from multi_inst.core.commands import MSPCommand
from multi_inst.core.diagnostics import DiagConfig, write_result
from multi_inst.io.serial_manager import list_candidate_ports


class FakeSerial:
    def __init__(self, response: bytes):
        self._buffer = bytearray(response)
        self.written = bytearray()
        self.timeout = 0.3
        self.dtr = False
        self.rts = False

    def read(self, size: int) -> bytes:
        if not self._buffer:
            time.sleep(0.001)
            return b""
        chunk = self._buffer[:size]
        del self._buffer[:size]
        return bytes(chunk)

    def write(self, data: bytes) -> int:
        self.written.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:  # pragma: no cover - parity with serial.Serial
        pass


def make_response(command: int, payload: bytes) -> bytes:
    frame = msp.MSPFrame(command=command, payload=payload)
    data = frame.to_bytes()
    # convert to response direction
    return b"$M" + bytes([msp.DIR_FROM_FC]) + data[3:]


def test_build_frame_roundtrip():
    frame = msp.build_frame(42, b"abc")
    encoded = frame.to_bytes()
    expected_checksum = msp._xor_checksum(3, 42, b"abc")  # type: ignore[attr-defined]
    assert encoded == b"$M<\x03*abc" + bytes([expected_checksum])


def test_msp_client_request_reads_payload():
    payload = b"\x01\x02\x03"
    response = make_response(MSPCommand.MSP_STATUS, payload)
    serial_port = FakeSerial(response)
    client = msp.MSPClient(serial_port)
    serial_port.dtr = True
    serial_port.rts = True
    client.wake()
    result = client.request(MSPCommand.MSP_STATUS)
    assert result == payload
    assert serial_port.written.startswith(b"$M<")


def test_write_result_allocates_defect(tmp_path):
    config = DiagConfig(out_dir=tmp_path)
    payload = {"port": "/dev/null", "baud": 115200, "ok": False, "reasons": ["fail"]}
    path = write_result(config.out_dir, payload)
    assert path.exists()
    assert path.name.startswith("DEFECT-")


def test_list_candidate_ports(monkeypatch):
    monkeypatch.setattr("glob.glob", lambda pattern: [f"{pattern[:-1]}0", f"{pattern[:-1]}1"])
    ports = list_candidate_ports(["/dev/ttyACM*", "/dev/ttyACM*"])
    assert sorted(ports) == ["/dev/ttyACM0", "/dev/ttyACM1"]
