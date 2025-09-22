"""Analysis helpers to evaluate flight controllers."""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List

from .utils import RollingStats


@dataclass
class LoopStatistics:
    samples: int
    mean_us: float
    std_us: float
    min_us: float
    max_us: float
    p95: float
    p99: float
    loop_hz: float


@dataclass
class ImuStatistics:
    samples: int
    gyro_std: List[float]
    gyro_bias: List[float]
    acc_norm_std: float


@dataclass
class DeviceAnalytics:
    loop_stats: LoopStatistics | None = None
    imu_stats: ImuStatistics | None = None
    i2c_error_rate: float = 0.0
    ok: bool = True
    reasons: List[str] = field(default_factory=list)


PROFILE_DEFAULTS = {
    "usb_stand": {
        "ignore_tilt": True,
        "max_gyro_std": 6.0,
        "max_gyro_bias": 12.0,
        "max_accnorm_std": 6.0,
        "max_cyc_jitter": 20.0,
        "max_i2c_errors": 0.0,
    },
    "field_strict": {
        "ignore_tilt": False,
        "max_gyro_std": 4.0,
        "max_gyro_bias": 8.0,
        "max_accnorm_std": 4.0,
        "max_cyc_jitter": 10.0,
        "max_i2c_errors": 0.0,
    },
}


class LoopAnalyzer:
    def __init__(self, window: float = 60.0) -> None:
        self.window = window
        self.samples: Deque[tuple[float, float]] = deque()
        self.stats = RollingStats(window=int(window))

    def add_sample(self, cycle_time_us: float, ts: float | None = None) -> None:
        if ts is None:
            ts = time.time()
        self.samples.append((ts, cycle_time_us))
        self.stats.add(cycle_time_us, ts)
        self._evict(ts)

    def _evict(self, now: float) -> None:
        while self.samples and now - self.samples[0][0] > self.window:
            self.samples.popleft()

    def snapshot(self) -> LoopStatistics | None:
        if not self.samples:
            return None
        mean_us = self.stats.mean()
        std_us = self.stats.std()
        min_us = self.stats.min()
        max_us = self.stats.max()
        p95, p99 = self.stats.percentiles(95, 99)
        loop_hz = 0.0 if mean_us == 0 else 1_000_000.0 / mean_us
        return LoopStatistics(
            samples=len(self.samples),
            mean_us=mean_us,
            std_us=std_us,
            min_us=min_us,
            max_us=max_us,
            p95=p95,
            p99=p99,
            loop_hz=loop_hz,
        )


class ImuAnalyzer:
    def __init__(self, window: float = 30.0) -> None:
        self.window = window
        self.samples: Deque[
            tuple[float, tuple[int, int, int], tuple[int, int, int]]
        ] = deque()

    def add_sample(
        self,
        gyro: tuple[int, int, int],
        acc: tuple[int, int, int],
        ts: float | None = None,
    ) -> None:
        if ts is None:
            ts = time.time()
        self.samples.append((ts, gyro, acc))
        self._evict(ts)

    def _evict(self, now: float) -> None:
        while self.samples and now - self.samples[0][0] > self.window:
            self.samples.popleft()

    def snapshot(self, gyro_scale: float = 1.0) -> ImuStatistics | None:
        if not self.samples:
            return None
        gyro_values = list(zip(*(sample[1] for sample in self.samples)))
        acc_values = list(zip(*(sample[2] for sample in self.samples)))
        gyro_std = [statistics_std(axis) * gyro_scale for axis in gyro_values]
        gyro_bias = [statistics_mean(axis) * gyro_scale for axis in gyro_values]
        acc_norms = [vector_norm(acc) for acc in zip(*acc_values)]
        acc_norm_std = statistics_std(tuple(acc_norms))
        return ImuStatistics(
            samples=len(self.samples),
            gyro_std=gyro_std,
            gyro_bias=gyro_bias,
            acc_norm_std=acc_norm_std,
        )


def evaluate(
    profile: str,
    loop_stats: LoopStatistics | None,
    imu_stats: ImuStatistics | None,
    i2c_error_rate: float,
) -> DeviceAnalytics:
    profile_cfg = PROFILE_DEFAULTS.get(profile, PROFILE_DEFAULTS["usb_stand"])
    analytics = DeviceAnalytics(
        loop_stats=loop_stats, imu_stats=imu_stats, i2c_error_rate=i2c_error_rate
    )
    reasons: List[str] = []
    ok = True
    if loop_stats:
        jitter = loop_stats.std_us
        if jitter > profile_cfg["max_cyc_jitter"]:
            ok = False
            reasons.append(
                f"loop jitter {jitter:.2f} > {profile_cfg['max_cyc_jitter']}"
            )
    if imu_stats:
        for axis, std_val in zip("xyz", imu_stats.gyro_std):
            if std_val > profile_cfg["max_gyro_std"]:
                ok = False
                reasons.append(
                    f"gyro_std_{axis} {std_val:.2f} > {profile_cfg['max_gyro_std']}"
                )
        for axis, bias_val in zip("xyz", imu_stats.gyro_bias):
            if abs(bias_val) > profile_cfg["max_gyro_bias"]:
                ok = False
                reasons.append(
                    f"gyro_bias_{axis} {bias_val:.2f} > {profile_cfg['max_gyro_bias']}"
                )
        if imu_stats.acc_norm_std > profile_cfg["max_accnorm_std"]:
            ok = False
            reasons.append(
                f"acc_norm_std {imu_stats.acc_norm_std:.2f} > {profile_cfg['max_accnorm_std']}"
            )
    if i2c_error_rate > profile_cfg["max_i2c_errors"]:
        ok = False
        reasons.append(
            f"i2c_error_rate {i2c_error_rate:.2f} > {profile_cfg['max_i2c_errors']}"
        )
    analytics.ok = ok
    analytics.reasons = reasons
    return analytics


def statistics_std(values: tuple[int, ...] | tuple[float, ...]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(variance)


def statistics_mean(values: tuple[int, ...] | tuple[float, ...]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def vector_norm(vector: tuple[int, ...] | tuple[float, ...]) -> float:
    return math.sqrt(sum(v * v for v in vector))
