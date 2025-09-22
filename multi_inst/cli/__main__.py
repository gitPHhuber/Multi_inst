from __future__ import annotations

"""Console script entry point forwarding to :mod:`multi_inst.cli.diag`."""

from .diag import main

__all__ = ["main"]


if __name__ == "__main__":  # pragma: no cover - convenience execution
    raise SystemExit(main())
