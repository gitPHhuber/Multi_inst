"""Console script entry point forwarding to :mod:`multi_inst.cli.diag`."""

from __future__ import annotations

from .diag import main

__all__ = ["main"]


if __name__ == "__main__":  # pragma: no cover - convenience execution
    raise SystemExit(main())
