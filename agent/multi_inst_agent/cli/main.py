"""Command line interface for the Multi Inst agent."""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import List

from ..api.app import manager
from ..io.json_writer import ReportWriter
from ..io.ports import PortFilterConfig, list_port_strings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multi-inst", description="Multi Inst diagnostic agent"
    )
    parser.add_argument("ports", nargs="*", help="Serial ports to inspect")
    parser.add_argument("--out", default="./out", help="Output directory")
    parser.add_argument(
        "--workers", type=int, default=4, help="Number of worker coroutines"
    )
    parser.add_argument("--baud", type=int, default=1_000_000, help="Baud rate")
    parser.add_argument("--record", help="Path to MSP record file (.msp.zst)")
    parser.add_argument("--profile", default="usb_stand", help="Analysis profile")
    parser.add_argument("--mode", choices=["normal", "pro"], default="normal")
    parser.add_argument("--auto", dest="auto", action="store_true", help="Auto test flow")
    parser.add_argument("--no-auto", dest="auto", action="store_false", help="Disable auto flow")
    parser.set_defaults(auto=True)
    parser.add_argument(
        "--duration", type=float, default=5.0, help="Duration of polling in seconds"
    )
    parser.add_argument("--simulate", action="store_true", help="Use simulated devices")
    parser.add_argument(
        "--disable-whitelist",
        action="store_true",
        help="Allow all ports regardless of VID/PID",
    )
    parser.add_argument(
        "--include-sim",
        action="store_true",
        help="Include sim:// ports when scanning",
    )
    return parser


async def run_cli(args: argparse.Namespace) -> int:
    port_cfg = PortFilterConfig(
        enforce_whitelist=not args.disable_whitelist,
        include_simulated=args.include_sim or args.simulate,
    )
    ports: List[str] = args.ports or list_port_strings(port_cfg)
    session = manager.start_session(
        ports,
        args.baud,
        args.profile,
        args.mode,
        args.auto,
        args.simulate,
        args.out,
        port_cfg,
        args.duration,
    )
    start = time.time()
    try:
        while time.time() - start < args.duration:
            await asyncio.sleep(0.5)
    finally:
        snapshot = session.snapshot()
        await manager.stop_session(session.id)
        writer = ReportWriter(args.out)
        writer.summary = list(manager.reports.values()) or snapshot
        writer.write_summary()
        for device in snapshot:
            uid = device.get("uid") or device.get("port")
            status = "OK" if device.get("ok") else "NOT OK"
            reasons = ", ".join(device.get("reasons", [])) or ""
            print(f"{uid}: {status} {reasons}")
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(run_cli(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
