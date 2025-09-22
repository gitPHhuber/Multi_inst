"""Console entry point for the ``multi-inst`` command."""

from __future__ import annotations

import sys

from .diag import main


def entry() -> int:
    """Return the process exit code for the CLI."""

    return main()


def _run() -> None:
    sys.exit(entry())


if __name__ == "__main__":  # pragma: no cover - entry point
    _run()
