"""PySide6 powered real-time dashboard for the Multi Inst toolkit."""

from __future__ import annotations

import argparse
import sys
from typing import Iterable, List

from PySide6 import QtWidgets

from multi_inst.core.diagnostics import handshake
from multi_inst.core.msp import MSPClient
from multi_inst.io.serial_manager import list_candidate_ports

from .data_models import DeviceIdentity
from .data_sources import LiveSerialSource, build_simulated_sources
from .device_manager import DeviceManager
from .main_window import MainWindow

try:  # pragma: no cover - optional dependency for GUI usage only
    import serial  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    serial = None  # type: ignore[assignment]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi Inst GUI")
    parser.add_argument(
        "--sim",
        action="store_true",
        help="Run the GUI in simulator mode (no hardware required).",
    )
    parser.add_argument(
        "--ports",
        nargs="*",
        help="Serial ports to monitor (defaults to auto discovery)",
    )
    parser.add_argument("--baud", type=int, default=1_000_000, help="Serial baud rate")
    parser.add_argument("--loop-hz", type=float, default=30.0, help="Target polling frequency")
    parser.add_argument(
        "--sim-count",
        type=int,
        default=3,
        help="Number of simulated devices when running with --sim",
    )
    return parser


def _build_live_sources(ports: Iterable[str], baud: int, loop_hz: float) -> List[LiveSerialSource]:
    if serial is None:
        raise RuntimeError("pyserial is required for live telemetry mode")
    sources: List[LiveSerialSource] = []
    for port in ports:
        identity = _probe_identity(port, baud)
        sources.append(
            LiveSerialSource(
                identity,
                port=port,
                baud=baud,
                target_hz=loop_hz,
            )
        )
    return sources


def _probe_identity(port: str, baud: int) -> DeviceIdentity:
    if serial is None:
        return DeviceIdentity(port=port, uid=port)
    try:
        with serial.Serial(port, baudrate=baud, timeout=0.3) as handle:
            client = MSPClient(handle, inter_command_gap=0.01, retries=2)
            client.wake()
            info = handshake(client)
    except Exception:  # noqa: BLE001 - handshake best effort
        return DeviceIdentity(port=port, uid=port)
    uid = str(info.get("uid") or info.get("board_uid") or port)
    return DeviceIdentity(
        port=port,
        uid=uid,
        variant=info.get("fc_variant"),
        version=info.get("fc_version"),
        board=info.get("board_id"),
    )


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.sim:
        sources = build_simulated_sources(args.sim_count)
    else:
        ports = args.ports or list_candidate_ports()
        if not ports:
            parser.error("no candidate serial ports discovered; use --sim for demo mode")
        sources = _build_live_sources(ports, args.baud, args.loop_hz)

    app = QtWidgets.QApplication(sys.argv or ["multi-inst-gui"])
    manager = DeviceManager(sources)
    window = MainWindow(manager)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
