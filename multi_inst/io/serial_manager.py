"""Helpers for discovering serial ports and orchestrating diagnostics workers."""

from __future__ import annotations

import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency guard for unit tests
    import serial  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - serial is required in production
    serial = None  # type: ignore[assignment]

from multi_inst.core.diagnostics import (
    DiagConfig,
    diagnose_port,
    ensure_out_dir,
    summarise,
    write_result,
    write_summary,
)
from multi_inst.core.msp import MSPClient

DEFAULT_PATTERNS = ("/dev/ttyACM*", "/dev/ttyUSB*")


def list_candidate_ports(patterns: Iterable[str] = DEFAULT_PATTERNS) -> List[str]:
    ports: List[str] = []
    for pattern in patterns:
        ports.extend(glob.glob(pattern))
    return sorted(set(ports))


class SerialManager:
    """Coordinate diagnostics execution across multiple serial ports."""

    def __init__(self, ports: Sequence[str], workers: int = 4) -> None:
        self._ports = list(ports)
        self._workers = max(1, workers)

    def run(
        self,
        config: DiagConfig,
        *,
        callback: Optional[Callable[[dict], None]] = None,
    ) -> Tuple[List[dict], List[dict]]:
        ensure_out_dir(config.out_dir)
        summaries: List[dict] = []
        results: List[dict] = []
        with ThreadPoolExecutor(max_workers=self._workers) as executor:
            futures = {
                executor.submit(self._process_port, port, config): port for port in self._ports
            }
            for future in as_completed(futures):
                result, summary = future.result()
                results.append(result)
                summaries.append(summary)
                if callback is not None:
                    callback(summary)
        write_summary(config.out_dir, summaries)
        return results, summaries

    def _process_port(self, port: str, config: DiagConfig) -> Tuple[dict, dict]:
        if serial is None:
            raise RuntimeError("pyserial is not installed")
        try:
            serial_port = serial.Serial(port, baudrate=config.baud, timeout=0.3)
        except serial.SerialException as exc:
            payload = {
                "port": port,
                "baud": config.baud,
                "ok": False,
                "reasons": [f"serial error: {exc}"],
                "error": f"SerialException: {exc}",
            }
            path = write_result(config.out_dir, payload)
            summary = summarise(path, payload)
            return payload, summary

        try:
            client = MSPClient(serial_port, inter_command_gap=0.01, retries=3)
            result, summary = diagnose_port(port, client, config)
            return result, summary
        finally:
            serial_port.close()
