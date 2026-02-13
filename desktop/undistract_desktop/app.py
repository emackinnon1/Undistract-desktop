from __future__ import annotations

import threading
from typing import List

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .blocklist_store import BlocklistStore
from .websocket_server import LocalWebSocketServer


class UiSignals(QObject):
    ble_status_changed = pyqtSignal(str)
    ble_devices_changed = pyqtSignal(list)


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Undistract Desktop")
        self._store = BlocklistStore()
        self._signals = UiSignals()
        self._signals.ble_status_changed.connect(self._set_ble_status)
        self._signals.ble_devices_changed.connect(self._set_ble_devices)
        self._server = LocalWebSocketServer(
            on_ble_status=self._signals.ble_status_changed.emit,
            on_ble_devices=self._signals.ble_devices_changed.emit,
        )
        self._server_thread = threading.Thread(target=self._server.run_forever, daemon=True)
        self._server_thread.start()
        self._blocking_checkbox = QCheckBox("Blocking enabled")
        self._blocking_checkbox.stateChanged.connect(self._on_blocking_changed)

        self._domain_input = QLineEdit()
        self._domain_input.setPlaceholderText("Add domain (e.g., example.com)")
        self._add_button = QPushButton("Add")
        self._add_button.clicked.connect(self._add_domain)

        self._list = QListWidget()
        self._remove_button = QPushButton("Remove selected")
        self._remove_button.clicked.connect(self._remove_selected)

        self._ble_status = QLabel("BLE: starting")
        self._ble_devices = QListWidget()
        self._ble_devices.setMinimumHeight(120)
        self._ble_devices_label = QLabel("Nearby BLE devices")

        input_row = QHBoxLayout()
        input_row.addWidget(self._domain_input)
        input_row.addWidget(self._add_button)

        layout = QVBoxLayout()
        layout.addWidget(self._blocking_checkbox)
        layout.addLayout(input_row)
        layout.addWidget(self._list)
        layout.addWidget(self._remove_button)
        layout.addWidget(self._ble_status)
        layout.addWidget(self._ble_devices_label)
        layout.addWidget(self._ble_devices)

        self.setLayout(layout)
        self._load_state()

    def _load_state(self) -> None:
        state = self._store.load()
        self._blocking_checkbox.setChecked(state.blocking)
        self._list.clear()
        for domain in state.domains:
            self._list.addItem(QListWidgetItem(domain))

    def _on_blocking_changed(self, state: int) -> None:
        blocking = state == Qt.CheckState.Checked.value
        self._store.set_blocking(blocking)

    def _add_domain(self) -> None:
        text = self._domain_input.text().strip().lower()
        if not text:
            return
        domains = self._current_domains()
        if text not in domains:
            domains.append(text)
            self._store.set_domains(domains)
            self._list.addItem(QListWidgetItem(text))
        self._domain_input.clear()

    def _remove_selected(self) -> None:
        selected = self._list.selectedItems()
        if not selected:
            return
        domains = self._current_domains()
        for item in selected:
            if item.text() in domains:
                domains.remove(item.text())
            self._list.takeItem(self._list.row(item))
        self._store.set_domains(domains)

    def _current_domains(self) -> List[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]

    def _set_ble_status(self, status: str) -> None:
        self._ble_status.setText(status)

    def _set_ble_devices(self, devices: List[str]) -> None:
        self._ble_devices.clear()
        for name in devices:
            self._ble_devices.addItem(QListWidgetItem(name))


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    window.resize(520, 480)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
