"""Polling scheduler for MSP commands."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class CommandRate:
    cmd: int
    hz: float


@dataclass
class Scheduler:
    commands: List[CommandRate]
    last_run: Dict[int, float] = field(default_factory=dict)

    def due(self, now: float | None = None) -> List[int]:
        if now is None:
            now = time.time()
        due_cmds: List[int] = []
        for rate in self.commands:
            period = 1.0 / rate.hz if rate.hz > 0 else 0
            last = self.last_run.get(rate.cmd, 0.0)
            if period == 0 or now - last >= period:
                due_cmds.append(rate.cmd)
                self.last_run[rate.cmd] = now
        return due_cmds

    def update_rate(self, cmd: int, hz: float) -> None:
        for rate in self.commands:
            if rate.cmd == cmd:
                rate.hz = hz
                return
        self.commands.append(CommandRate(cmd, hz))


DEFAULT_RATES = {
    "status_hz": 10,
    "attitude_hz": 25,
    "raw_imu_hz": 50,
    "analog_hz": 5,
    "rc_hz": 5,
    "motor_hz": 5,
    "voltage_hz": 2,
    "current_hz": 2,
    "battery_hz": 2,
    "dataflash_hz": 1,
    "esc_hz": 1,
}


COMMAND_RATE_MAP = {
    "status_hz": 101,
    "attitude_hz": 108,
    "raw_imu_hz": 102,
    "analog_hz": 110,
    "rc_hz": 105,
    "motor_hz": 104,
    "voltage_hz": 128,
    "current_hz": 129,
    "battery_hz": 130,
    "dataflash_hz": 70,
    "esc_hz": 134,
}


def build_scheduler(rates: Dict[str, float] | None = None) -> Scheduler:
    rates = rates or {}
    commands: List[CommandRate] = []
    for key, default_hz in DEFAULT_RATES.items():
        hz = float(rates.get(key, default_hz))
        if hz <= 0:
            continue
        cmd = COMMAND_RATE_MAP[key]
        commands.append(CommandRate(cmd=cmd, hz=hz))
    return Scheduler(commands=commands)
