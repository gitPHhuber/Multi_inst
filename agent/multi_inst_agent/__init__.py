"""Multi Inst Agent package."""

from importlib.metadata import version, PackageNotFoundError

__all__ = ["__version__"]

try:
    __version__ = version("multi-inst-agent")
except PackageNotFoundError:  # pragma: no cover - during local dev without install
    __version__ = "0.0.0"
