"""Dashboard view with device tiles and sparklines."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from ..data_models import DeviceIdentity, TelemetryFrame


class DeviceCardWidget(QtWidgets.QFrame):
    clicked = QtCore.Signal(str)

    def __init__(self, identity: DeviceIdentity, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.identity = identity
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setObjectName("device-card")
        self.setMinimumWidth(280)

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        self._title = QtWidgets.QLabel(f"{identity.uid}")
        self._title.setStyleSheet("font-weight: bold; font-size: 16px;")
        header.addWidget(self._title)
        header.addStretch(1)
        self._status_indicator = QtWidgets.QLabel("●")
        self._status_indicator.setStyleSheet("color: #0f0; font-size: 18px;")
        header.addWidget(self._status_indicator)
        layout.addLayout(header)

        info_grid = QtWidgets.QFormLayout()
        self._variant = QtWidgets.QLabel(identity.variant or "—")
        self._version = QtWidgets.QLabel(identity.version or "—")
        self._board = QtWidgets.QLabel(identity.board or "—")
        info_grid.addRow("Variant", self._variant)
        info_grid.addRow("Version", self._version)
        info_grid.addRow("Board", self._board)
        layout.addLayout(info_grid)

        self._spark_cycle = _Sparkline("Loop Hz", color="#55acee")
        self._spark_vbat = _Sparkline("VBat", color="#f39c12")
        self._spark_amps = _Sparkline("Amps", color="#e74c3c")
        layout.addWidget(self._spark_cycle)
        layout.addWidget(self._spark_vbat)
        layout.addWidget(self._spark_amps)

        layout.addStretch(1)
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # pragma: no cover - GUI event
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self.identity.port)
        super().mousePressEvent(event)

    def update_identity(self, identity: DeviceIdentity) -> None:
        self.identity = identity
        self._title.setText(identity.uid)
        self._variant.setText(identity.variant or "—")
        self._version.setText(identity.version or "—")
        self._board.setText(identity.board or "—")

    def update_frame(self, frame: TelemetryFrame, history: Iterable[TelemetryFrame]) -> None:
        loop_hz = frame.value("status.cycleTime_us")
        hz = 1_000_000 / loop_hz if loop_hz else None
        vbat = frame.value("analog.vbat_V")
        amps = frame.value("analog.amperage_A")
        self._status_indicator.setStyleSheet(
            "color: #0f0; font-size: 18px;" if frame.status else "color: #f00; font-size: 18px;"
        )
        self._spark_cycle.append(hz)
        self._spark_vbat.append(vbat)
        self._spark_amps.append(amps)


class _Sparkline(QtWidgets.QWidget):
    def __init__(self, title: str, *, color: str, history: int = 120, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._history: List[Optional[float]] = []
        self._capacity = history
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(title_label)
        self._plot = pg.PlotWidget(background="transparent")
        self._plot.setFixedHeight(80)
        self._plot.hideAxis("left")
        self._plot.hideAxis("bottom")
        self._curve = self._plot.plot(pen=pg.mkPen(color=color, width=2))
        layout.addWidget(self._plot)

    def append(self, value: Optional[float]) -> None:
        if value is None:
            return
        self._history.append(value)
        if len(self._history) > self._capacity:
            self._history = self._history[-self._capacity :]
        self._curve.setData(self._history)


class DashboardView(QtWidgets.QScrollArea):
    """Scrollable grid of :class:`DeviceCardWidget` instances."""

    device_selected = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        container = QtWidgets.QWidget()
        self._grid = QtWidgets.QGridLayout(container)
        self._grid.setSpacing(12)
        self._cards: Dict[str, DeviceCardWidget] = {}
        self.setWidget(container)

    def add_device(self, identity: DeviceIdentity) -> None:
        card = DeviceCardWidget(identity)
        card.clicked.connect(self.device_selected)  # type: ignore[arg-type]
        row = len(self._cards) // 2
        col = len(self._cards) % 2
        self._grid.addWidget(card, row, col)
        self._cards[identity.port] = card

    def remove_device(self, port: str) -> None:
        card = self._cards.pop(port, None)
        if not card:
            return
        card.setParent(None)
        card.deleteLater()

    def update_frame(self, port: str, frame: TelemetryFrame, history: Iterable[TelemetryFrame]) -> None:
        card = self._cards.get(port)
        if not card:
            return
        card.update_frame(frame, history)

