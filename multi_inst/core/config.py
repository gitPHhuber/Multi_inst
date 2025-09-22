"""Helpers for loading CLI/GU diagnostics configuration profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping

from ruamel.yaml import YAML


class ProfileError(RuntimeError):
    """Raised when the configuration file or requested profile is invalid."""


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

_yaml = YAML(typ="safe")


def load_profiles(path: Path | None = None) -> Dict[str, Mapping[str, object]]:
    """Return the profile mapping stored in ``config.yaml``.

    Parameters
    ----------
    path:
        Optional path to a YAML configuration file. When omitted the built-in
        ``config.yaml`` packaged alongside :mod:`multi_inst` is used.
    """

    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise ProfileError(f"configuration file not found: {config_path}")
    data = _yaml.load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "profiles" not in data:
        raise ProfileError("config file must contain a 'profiles' mapping")
    profiles = data["profiles"]
    if not isinstance(profiles, dict):
        raise ProfileError("'profiles' must be a mapping")
    normalized: Dict[str, Mapping[str, object]] = {}
    for name, profile in profiles.items():
        if not isinstance(profile, Mapping):
            raise ProfileError(f"profile '{name}' must be a mapping")
        normalized[name] = profile
    return normalized


@dataclass(frozen=True)
class Profile:
    """Concrete configuration profile resolved from YAML."""

    name: str
    ignore_tilt: bool
    max_tilt: float
    max_gyro_std: float
    max_gyro_bias: float
    max_accnorm_std: float
    max_cyc_jitter: int
    max_i2c_errors: int
    sample_rates: Mapping[str, object]

    @classmethod
    def from_mapping(cls, name: str, data: Mapping[str, object]) -> "Profile":
        required = (
            "ignore_tilt",
            "max_tilt",
            "max_gyro_std",
            "max_gyro_bias",
            "max_accnorm_std",
            "max_cyc_jitter",
            "max_i2c_errors",
        )
        missing = [key for key in required if key not in data]
        if missing:
            raise ProfileError(f"profile '{name}' is missing required keys: {', '.join(missing)}")
        sample_rates = data.get("sample_rates", {})
        if not isinstance(sample_rates, Mapping):
            raise ProfileError(f"profile '{name}' sample_rates must be a mapping")
        return cls(
            name=name,
            ignore_tilt=bool(data["ignore_tilt"]),
            max_tilt=float(data["max_tilt"]),
            max_gyro_std=float(data["max_gyro_std"]),
            max_gyro_bias=float(data["max_gyro_bias"]),
            max_accnorm_std=float(data["max_accnorm_std"]),
            max_cyc_jitter=int(data["max_cyc_jitter"]),
            max_i2c_errors=int(data["max_i2c_errors"]),
            sample_rates=dict(sample_rates),
        )


def resolve_profile(name: str, profiles: Mapping[str, Mapping[str, object]]) -> Profile:
    """Resolve *name* from *profiles* and return a :class:`Profile`."""

    if name not in profiles:
        available = ", ".join(sorted(profiles)) or "<none>"
        raise ProfileError(f"unknown profile '{name}'. available: {available}")
    return Profile.from_mapping(name, profiles[name])
