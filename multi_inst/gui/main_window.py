"""Main application window for the Multi Inst GUI."""

from __future__ import annotations

from typing import Dict, Optional

from PySide6 import QtCore, QtWidgets

from .data_models import DeviceIdentity, TelemetryFrame
from .device_manager import DeviceManager
from .views import DashboardView, DeviceDetailsView


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, manager: DeviceManager, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Multi Inst – Flight Controller Monitor")
        self.resize(1400, 800)
        self._manager = manager
        self._selected_port: Optional[str] = None
        self._identities: Dict[str, DeviceIdentity] = {}

        toolbar = self.addToolBar("Controls")
        toolbar.setMovable(False)
        self._start_action = toolbar.addAction("Start")
        self._stop_action = toolbar.addAction("Stop")
        toolbar.addSeparator()
        toolbar.addWidget(QtWidgets.QLabel("Profile:"))
        self._profile = QtWidgets.QComboBox()
        self._profile.addItems(["usb_stand", "field_strict"])
        toolbar.addWidget(self._profile)
        self._status_label = QtWidgets.QLabel("Idle")
        toolbar.addWidget(self._status_label)

        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Horizontal)
        self._dashboard = DashboardView()
        self._details = DeviceDetailsView()
        splitter.addWidget(self._dashboard)
        splitter.addWidget(self._details)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._dashboard.device_selected.connect(self._select_device)  # type: ignore[arg-type]
        manager.device_added.connect(self._on_device_added)  # type: ignore[arg-type]
        manager.device_removed.connect(self._on_device_removed)
        manager.telemetry_updated.connect(self._on_telemetry)  # type: ignore[arg-type]

        self._start_action.triggered.connect(self._resume)  # type: ignore[arg-type]
        self._stop_action.triggered.connect(self._pause)  # type: ignore[arg-type]
        self._profile.currentTextChanged.connect(self._on_profile_changed)  # type: ignore[arg-type]
        self._paused = False
        self.statusBar().showMessage("Ready")

    def _resume(self) -> None:
        self._paused = False
        self._status_label.setText("Live")
        self.statusBar().showMessage("Live telemetry")

    def _pause(self) -> None:
        self._paused = True
        self._status_label.setText("Paused")
        self.statusBar().showMessage("Paused – telemetry frozen")

    def _on_profile_changed(self, profile: str) -> None:
        self.statusBar().showMessage(f"Profile selected: {profile}")

    def _select_device(self, port: str) -> None:
        self._selected_port = port
        identity = self._identities.get(port)
        if identity:
            self._details.set_device(identity)
        history = self._manager.histories(port)
        if history:
            self._details.update_frame(history[-1], history)

    def _on_device_added(self, identity: DeviceIdentity) -> None:
        self._identities[identity.port] = identity
        self._dashboard.add_device(identity)
        if self._selected_port is None:
            self._select_device(identity.port)

    def _on_device_removed(self, port: str) -> None:
        self._dashboard.remove_device(port)
        self._identities.pop(port, None)
        if self._selected_port == port:
            self._selected_port = None
            self._details.set_device(DeviceIdentity(port="—", uid="No device"))

    def _on_telemetry(self, port: str, frame: TelemetryFrame) -> None:
        if self._paused:
            return
        self._dashboard.update_frame(port, frame, self._manager.histories(port))
        if port == self._selected_port:
            history = self._manager.histories(port)
            self._details.update_frame(frame, history)

