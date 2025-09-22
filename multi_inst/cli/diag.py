"""Command line entry point for the multi-instance MSP diagnostics tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from multi_inst.core.config import ProfileError, load_profiles, resolve_profile
from multi_inst.core.diagnostics import DiagConfig
from multi_inst.io.serial_manager import SerialManager, list_candidate_ports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-FC MSP diagnostics")
    parser.add_argument("--out", default="./out", help="Output directory for JSON reports")
    parser.add_argument("--config", help="Path to config.yaml overriding defaults")
    parser.add_argument(
        "--profile",
        default="usb_stand",
        help="Diagnostics profile defined in config.yaml",
    )
    parser.add_argument("--workers", type=int, default=4, help="Number of worker threads")
    parser.add_argument("--baud", type=int, default=1_000_000, help="Serial baud rate")
    parser.add_argument("--imu-sec", type=float, default=3.0, help="Seconds of IMU sampling")
    parser.add_argument("--status-samples", type=int, default=50, help="Number of MSP_STATUS polls")
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="Emit JSON lines instead of human readable output",
    )
    parser.add_argument("--max-gyro-std", type=float, help="Override profile limit")
    parser.add_argument("--max-gyro-bias", type=float, help="Override profile limit")
    parser.add_argument("--max-accnorm-std", type=float, help="Override profile limit")
    parser.add_argument("--max-cyc-jitter", type=int, help="Override profile limit")
    parser.add_argument("--max-i2c-errors", type=int, help="Override profile limit")
    parser.add_argument("--max-tilt", type=float, help="Override profile limit")
    parser.add_argument(
        "--ignore-tilt",
        action="store_true",
        default=None,
        help="Force ignore tilt regardless of profile",
    )
    parser.add_argument("ports", nargs="*", help="Explicit list of serial ports to probe")
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    ports = args.ports or list_candidate_ports()
    if not ports:
        parser.error("no /dev/ttyACM* or /dev/ttyUSB* ports discovered")

    try:
        profiles = load_profiles(Path(args.config) if args.config else None)
        profile = resolve_profile(args.profile, profiles)
    except ProfileError as exc:
        parser.error(str(exc))

    config = DiagConfig.from_profile(
        out_dir=Path(args.out),
        baud=args.baud,
        imu_seconds=args.imu_sec,
        status_samples=args.status_samples,
        profile=profile,
        jsonl=args.jsonl,
    ).with_overrides(
        max_gyro_std=args.max_gyro_std,
        max_gyro_bias=args.max_gyro_bias,
        max_accnorm_std=args.max_accnorm_std,
        max_cyc_jitter=args.max_cyc_jitter,
        max_i2c_errors=args.max_i2c_errors,
        max_tilt=args.max_tilt,
        ignore_tilt=args.ignore_tilt,
    )

    manager = SerialManager(ports, workers=args.workers)

    def _emit(summary: dict) -> None:
        if args.jsonl:
            print(json.dumps(summary, ensure_ascii=False))
        else:
            port = summary.get("port")
            ok = summary.get("ok")
            uid = summary.get("uid")
            target = summary.get("file")
            print(f"[{port}] ok={ok} uid={uid} file={target}")

    _, summaries = manager.run(config, callback=_emit)
    exit_code = 0 if all(summary.get("ok") for summary in summaries) else 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
