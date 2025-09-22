"""Utility helpers for the Multi Inst agent."""

from __future__ import annotations

import math
import os
import time
from collections import deque
from statistics import mean, pstdev
from typing import Deque, Tuple


class RollingStats:
    """Maintain rolling statistics for numeric samples."""

    def __init__(self, window: int) -> None:
        self.window = window
        self._items: Deque[Tuple[float, float]] = deque()
        self._sum = 0.0
        self._sum_sq = 0.0

    def add(self, value: float, ts: float | None = None) -> None:
        if ts is None:
            ts = time.time()
        self._items.append((ts, value))
        self._sum += value
        self._sum_sq += value * value
        self._evict(ts)

    def _evict(self, now: float) -> None:
        while self._items and now - self._items[0][0] > self.window:
            _, value = self._items.popleft()
            self._sum -= value
            self._sum_sq -= value * value

    @property
    def count(self) -> int:
        return len(self._items)

    def mean(self) -> float:
        return self._sum / self.count if self.count else 0.0

    def std(self) -> float:
        if self.count < 2:
            return 0.0
        m = self.mean()
        variance = max(self._sum_sq / self.count - m * m, 0.0)
        return math.sqrt(variance)

    def min(self) -> float:
        if not self._items:
            return 0.0
        return min(value for _, value in self._items)

    def max(self) -> float:
        if not self._items:
            return 0.0
        return max(value for _, value in self._items)

    def percentiles(self, *percentiles: float) -> list[float]:
        if not self._items:
            return [0.0 for _ in percentiles]
        sorted_values = sorted(value for _, value in self._items)
        result = []
        for pct in percentiles:
            if not sorted_values:
                result.append(0.0)
                continue
            k = (len(sorted_values) - 1) * (pct / 100.0)
            f = math.floor(k)
            c = min(math.ceil(k), len(sorted_values) - 1)
            if f == c:
                result.append(sorted_values[int(k)])
            else:
                d0 = sorted_values[f] * (c - k)
                d1 = sorted_values[c] * (k - f)
                result.append(d0 + d1)
        return result


class ExposureCounter:
    """Track the number of values exceeding a threshold within a time window."""

    def __init__(self, window: float, sigma: float) -> None:
        self.window = window
        self.sigma = sigma
        self._values: Deque[Tuple[float, float]] = deque()
        self._mean = 0.0
        self._var = 0.0

    def add(self, value: float, ts: float | None = None) -> None:
        if ts is None:
            ts = time.time()
        self._values.append((ts, value))
        self._recompute()
        self._evict(ts)

    def _recompute(self) -> None:
        if not self._values:
            self._mean = 0.0
            self._var = 0.0
            return
        values = [value for _, value in self._values]
        self._mean = mean(values)
        self._var = pstdev(values) if len(values) > 1 else 0.0

    def _evict(self, now: float) -> None:
        changed = False
        while self._values and now - self._values[0][0] > self.window:
            self._values.popleft()
            changed = True
        if changed:
            self._recompute()

    def outliers(self) -> int:
        if not self._values:
            return 0
        threshold = self._mean + self.sigma * self._var
        return sum(1 for _, value in self._values if value > threshold)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def make_uid_name(uid: str | None, index: int) -> str:
    if uid:
        return f"{uid}.json"
    return f"DEFECT-{index:05d}.json"
