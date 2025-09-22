"""Qt integration for telemetry sources."""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, Iterable, List, Optional

from PySide6 import QtCore

from .data_models import DeviceIdentity, TelemetryFrame
from .data_sources import DeviceSource


class DeviceManager(QtCore.QObject):
    """Bridge between background telemetry workers and Qt widgets."""

    device_added = QtCore.Signal(DeviceIdentity)
    device_removed = QtCore.Signal(str)
    telemetry_updated = QtCore.Signal(str, TelemetryFrame)

    def __init__(self, sources: Iterable[DeviceSource], *, history_secs: float = 30.0) -> None:
        super().__init__()
        self._sources: Dict[str, DeviceSource] = {}
        self._history: Dict[str, Deque[TelemetryFrame]] = {}
        self._history_secs = history_secs
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(int(1000 / 30))
        self._timer.timeout.connect(self._drain_sources)  # type: ignore[arg-type]
        for source in sources:
            self.add_source(source)

    def add_source(self, source: DeviceSource) -> None:
        port = source.identity.port
        self._sources[port] = source
        self._history[port] = deque()
        self.device_added.emit(source.identity)
        source.start()
        if not self._timer.isActive():
            self._timer.start()

    def remove_source(self, port: str) -> None:
        source = self._sources.pop(port, None)
        if source is None:
            return
        source.stop()
        self._history.pop(port, None)
        self.device_removed.emit(port)
        if not self._sources:
            self._timer.stop()

    def histories(self, port: str) -> List[TelemetryFrame]:
        history = self._history.get(port, deque())
        return list(history)

    def latest(self, port: str) -> Optional[TelemetryFrame]:
        history = self._history.get(port)
        if not history:
            return None
        return history[-1]

    def _drain_sources(self) -> None:
        now = time.time()
        cutoff = now - self._history_secs
        for port, source in list(self._sources.items()):
            frame = source.queue.pop_latest()
            if not frame:
                continue
            history = self._history.setdefault(port, deque())
            history.append(frame)
            while history and history[0].timestamp < cutoff:
                history.popleft()
            self.telemetry_updated.emit(port, frame)

