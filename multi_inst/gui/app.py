"""Minimal GUI entry point placeholder for the Multi Inst toolkit."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi Inst GUI")
    parser.add_argument(
        "--sim",
        action="store_true",
        help="Run the GUI in simulator mode (no hardware required).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point used by the ``multi-inst-gui`` console script."""

    parser = build_parser()
    parser.parse_args(argv)
    # The real GUI is not implemented yet; provide a friendly placeholder.
    print("multi-inst GUI is not yet implemented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
