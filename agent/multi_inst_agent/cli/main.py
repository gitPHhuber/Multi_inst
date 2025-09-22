"""Command line interface for the Multi Inst agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import List

from ..api.app import SessionManager, manager
from ..io.json_writer import ReportWriter
from ..io.ports import list_port_strings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="multi-inst", description="Multi Inst diagnostic agent")
    parser.add_argument("ports", nargs="*", help="Serial ports to inspect")
    parser.add_argument("--out", default="./out", help="Output directory")
    parser.add_argument("--workers", type=int, default=4, help="Number of worker coroutines")
    parser.add_argument("--baud", type=int, default=1_000_000, help="Baud rate")
    parser.add_argument("--record", help="Path to MSP record file (.msp.zst)")
    parser.add_argument("--profile", default="usb_stand", help="Analysis profile")
    parser.add_argument("--duration", type=float, default=5.0, help="Duration of polling in seconds")
    parser.add_argument("--simulate", action="store_true", help="Use simulated devices")
    return parser


async def run_cli(args: argparse.Namespace) -> int:
    ports: List[str] = args.ports or list_port_strings()
    if not ports:
        ports = ["/dev/ttyACM0"]
    session = manager.start_session(ports, args.baud, args.profile, simulate=args.simulate or True)
    report_writer = ReportWriter(args.out)
    start = time.time()
    try:
        while time.time() - start < args.duration:
            await asyncio.sleep(0.5)
    finally:
        snapshot = session.snapshot()
        for device in snapshot:
            uid = device.get("uid")
            report_writer.write_report(uid, device)
        report_writer.write_summary()
        await manager.stop_session(session.id)
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(run_cli(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
