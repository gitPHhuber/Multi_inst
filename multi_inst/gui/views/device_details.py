"""Device detail view with live charts."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg

from ..data_models import DeviceIdentity, TelemetryFrame


def _stddev(values: List[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return variance ** 0.5


def _histogram(values: List[float], bins: int = 20) -> tuple[List[float], List[float]]:
    if not values:
        return [], []
    vmin = min(values)
    vmax = max(values)
    if vmin == vmax:
        return [len(values)], [vmin, vmax + 1]
    step = (vmax - vmin) / max(1, bins)
    edges = [vmin + i * step for i in range(bins + 1)]
    counts = [0.0 for _ in range(bins)]
    for value in values:
        idx = int((value - vmin) / step)
        if idx >= bins:
            idx = bins - 1
        counts[idx] += 1
    return counts, edges


class DeviceDetailsView(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self._header = QtWidgets.QLabel("Select a device on the dashboard")
        self._header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self._header)
        self._tabs = QtWidgets.QTabWidget()
        layout.addWidget(self._tabs, 1)

        self._overview = _OverviewTab()
        self._imu = _ImuTab()
        self._loop = _LoopTab()
        self._power = _PowerTab()
        self._raw = _RawTab()

        self._tabs.addTab(self._overview, "Overview")
        self._tabs.addTab(self._imu, "IMU")
        self._tabs.addTab(self._loop, "Loop")
        self._tabs.addTab(self._power, "Power")
        self._tabs.addTab(self._raw, "Raw")

    def set_device(self, identity: DeviceIdentity) -> None:
        self._header.setText(
            f"{identity.uid} — {identity.variant or '—'} {identity.version or ''} ({identity.port})"
        )
        self._overview.reset()
        self._imu.reset()
        self._loop.reset()
        self._power.reset()
        self._raw.reset()

    def update_frame(self, frame: TelemetryFrame, history: Iterable[TelemetryFrame]) -> None:
        frames = list(history)
        self._overview.update_frame(frame, frames)
        self._imu.update_history(frames)
        self._loop.update_history(frames)
        self._power.update_frame(frame)
        self._raw.update_frame(frame)


class _OverviewTab(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QFormLayout(self)
        self._hz = QtWidgets.QLabel("—")
        self._gyro = QtWidgets.QLabel("—")
        self._tilt = QtWidgets.QLabel("—")
        layout.addRow("Loop Hz", self._hz)
        layout.addRow("Gyro σ", self._gyro)
        layout.addRow("Tilt", self._tilt)

    def reset(self) -> None:
        self._hz.setText("—")
        self._gyro.setText("—")
        self._tilt.setText("—")

    def update_frame(self, frame: TelemetryFrame, history: List[TelemetryFrame]) -> None:
        loop = frame.value("status.cycleTime_us")
        hz = 1_000_000 / loop if loop else None
        if hz:
            self._hz.setText(f"{hz:.1f} Hz")
        gx, gy, gz = [], [], []
        for sample in history[-200:]:
            imu = sample.raw_imu
            if not isinstance(imu, dict):
                continue
            gx.append(imu.get("gx", 0))
            gy.append(imu.get("gy", 0))
            gz.append(imu.get("gz", 0))
        if gx:
            self._gyro.setText(
                ", ".join(
                    f"{_stddev(series):.1f}"
                    for series in (gx, gy, gz)
                )
            )
        else:
            self._gyro.setText("—")
        attitude = frame.attitude
        roll = attitude.get("roll_deg")
        pitch = attitude.get("pitch_deg")
        if isinstance(roll, (int, float)) and isinstance(pitch, (int, float)):
            self._tilt.setText(f"roll {roll:.1f}° | pitch {pitch:.1f}°")
        else:
            self._tilt.setText("—")


class _ImuTab(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        self._plot = pg.PlotWidget(title="Gyro (°/s)")
        self._plot.addLegend()
        self._plot.setYRange(-500, 500)
        self._gx = self._plot.plot(pen=pg.mkPen("#3498db", width=2), name="gx")
        self._gy = self._plot.plot(pen=pg.mkPen("#2ecc71", width=2), name="gy")
        self._gz = self._plot.plot(pen=pg.mkPen("#e74c3c", width=2), name="gz")
        layout.addWidget(self._plot, 1)

        self._acc_plot = pg.PlotWidget(title="Accelerometer norm (g)")
        self._acc_plot.setYRange(0, 3)
        self._acc_curve = self._acc_plot.plot(pen=pg.mkPen("#9b59b6", width=2))
        layout.addWidget(self._acc_plot, 1)

    def reset(self) -> None:
        self._gx.clear()
        self._gy.clear()
        self._gz.clear()
        self._acc_curve.clear()

    def update_history(self, history: List[TelemetryFrame]) -> None:
        gx, gy, gz, acc = [], [], [], []
        for frame in history[-600:]:
            imu = frame.raw_imu
            if not isinstance(imu, dict):
                continue
            gx.append(imu.get("gx", 0))
            gy.append(imu.get("gy", 0))
            gz.append(imu.get("gz", 0))
            ax = imu.get("ax", 0) / 512.0
            ay = imu.get("ay", 0) / 512.0
            az = imu.get("az", 0) / 512.0
            acc.append((ax**2 + ay**2 + az**2) ** 0.5)
        self._gx.setData(gx)
        self._gy.setData(gy)
        self._gz.setData(gz)
        self._acc_curve.setData(acc)


class _LoopTab(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        self._loop_plot = pg.PlotWidget(title="Cycle time (µs)")
        self._loop_curve = self._loop_plot.plot(pen=pg.mkPen("#1abc9c", width=2))
        layout.addWidget(self._loop_plot, 1)

        self._hist_plot = pg.PlotWidget(title="Cycle histogram")
        self._hist_curve = self._hist_plot.plot(stepMode=True, pen=pg.mkPen("#34495e", width=2))
        layout.addWidget(self._hist_plot, 1)

    def reset(self) -> None:
        self._loop_curve.clear()
        self._hist_curve.clear()

    def update_history(self, history: List[TelemetryFrame]) -> None:
        cycles: List[float] = []
        for frame in history[-600:]:
            cycle = frame.value("status.cycleTime_us")
            if cycle:
                cycles.append(cycle)
        if cycles:
            self._loop_curve.setData(cycles)
            y, x = _histogram(cycles)
            step_x: List[float] = []
            step_y: List[float] = []
            for idx, height in enumerate(y):
                left = x[idx]
                right = x[idx + 1]
                step_x.extend([left, right])
                step_y.extend([height, height])
            self._hist_curve.setData(step_x, step_y)
        else:
            self._hist_curve.clear()


class _PowerTab(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QFormLayout(self)
        self._vbat = QtWidgets.QLabel("—")
        self._amps = QtWidgets.QLabel("—")
        self._mah = QtWidgets.QLabel("—")
        layout.addRow("Voltage", self._vbat)
        layout.addRow("Current", self._amps)
        layout.addRow("Consumed", self._mah)

        self._meters = QtWidgets.QTableWidget(0, 4)
        self._meters.setHorizontalHeaderLabels(["ID", "Voltage (V)", "Current (A)", "Valid"])
        self._meters.horizontalHeader().setStretchLastSection(True)
        layout.addRow(QtWidgets.QLabel("Meters"), self._meters)

    def reset(self) -> None:
        self._vbat.setText("—")
        self._amps.setText("—")
        self._mah.setText("—")
        self._meters.setRowCount(0)

    def update_frame(self, frame: TelemetryFrame) -> None:
        vbat = frame.value("analog.vbat_V")
        amps = frame.value("analog.amperage_A")
        mah = frame.value("analog.mAh_drawn")
        if vbat is not None:
            self._vbat.setText(f"{vbat:.2f} V")
        if amps is not None:
            self._amps.setText(f"{amps:.2f} A")
        if mah is not None:
            self._mah.setText(f"{mah:.0f} mAh")

        meter_rows: List[Dict[str, object]] = []
        by_id: Dict[object, Dict[str, object]] = {}
        for meter in frame.voltage_meters:
            ident = meter.get("id", len(by_id))
            entry = dict(meter)
            entry.setdefault("current_A", "—")
            by_id[ident] = entry
        for meter in frame.current_meters:
            ident = meter.get("id", len(by_id))
            entry = by_id.setdefault(ident, {"id": ident})
            entry.update(meter)
        meter_rows = list(by_id.values())
        self._meters.setRowCount(len(meter_rows))
        for row, meter in enumerate(meter_rows):
            self._meters.setItem(row, 0, QtWidgets.QTableWidgetItem(str(meter.get("id", "—"))))
            self._meters.setItem(row, 1, QtWidgets.QTableWidgetItem(str(meter.get("voltage_V", "—"))))
            self._meters.setItem(row, 2, QtWidgets.QTableWidgetItem(str(meter.get("current_A", "—"))))
            invalid = meter.get("invalid")
            self._meters.setItem(row, 3, QtWidgets.QTableWidgetItem("no" if not invalid else "yes"))


class _RawTab(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        self._list = QtWidgets.QListWidget()
        layout.addWidget(self._list)

    def reset(self) -> None:
        self._list.clear()

    def update_frame(self, frame: TelemetryFrame) -> None:
        self._list.clear()
        for key, value in frame.raw_packets.items():
            self._list.addItem(f"{key}: {value}")

