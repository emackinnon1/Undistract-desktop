from __future__ import annotations

import logging
import logging.handlers
import threading
from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .blocklist_store import BlocklistStore
from .websocket_server import LocalWebSocketServer

# Set up logging to file so we can diagnose issues in the bundled app
_log_dir = Path.home() / "Library" / "Logs" / "Undistract"
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / "undistract.log"

_file_handler = logging.handlers.RotatingFileHandler(
    _log_file, maxBytes=2 * 1024 * 1024, backupCount=3,
)
_file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), _file_handler],
)

logger = logging.getLogger(__name__)
class UiSignals(QObject):
    ble_status_changed = pyqtSignal(str)
    ble_devices_changed = pyqtSignal(list)
    blocking_changed = pyqtSignal(bool)


class MainWindow(QWidget):
    def __init__(self, icon_path: Path) -> None:
        super().__init__()
        self.setWindowTitle("Undistract Desktop")
        self._icon = QIcon(str(icon_path))
        self.setWindowIcon(self._icon)
        self._store = BlocklistStore()
        self._signals = UiSignals()
        self._signals.ble_status_changed.connect(self._set_ble_status)
        self._signals.ble_devices_changed.connect(self._set_ble_devices)
        self._signals.blocking_changed.connect(self._set_blocking_state)
        self._tray_icon: QSystemTrayIcon | None = None
        self._tray_blocking_action: QAction | None = None
        self._server = LocalWebSocketServer(
            on_ble_status=self._signals.ble_status_changed.emit,
            on_ble_devices=self._signals.ble_devices_changed.emit,
            on_blocking_changed=self._signals.blocking_changed.emit,
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

    def setup_tray_icon(self) -> None:
        """Create and configure the system tray icon with menu."""
        self._tray_icon = QSystemTrayIcon(self._icon, parent=self)
        
        tray_menu = QMenu()
        
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self._show_window)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        self._tray_blocking_action = QAction("Blocking Enabled", self)
        self._tray_blocking_action.setCheckable(True)
        self._tray_blocking_action.triggered.connect(self._on_tray_blocking_toggled)
        tray_menu.addAction(self._tray_blocking_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        tray_menu.addAction(quit_action)
        
        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()
        
        # Sync tray menu with current blocking state
        state = self._store.load()
        self._tray_blocking_action.setChecked(state.blocking)

    def closeEvent(self, event) -> None:
        """Hide window instead of closing when user clicks close button."""
        event.ignore()
        self.hide()
        if self._tray_icon and self._tray_icon.isVisible():
            self._tray_icon.showMessage(
                "Undistract",
                "Application minimized to tray",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )

    def _show_window(self) -> None:
        """Show and activate the main window."""
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle tray icon activation (click)."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._show_window()

    def _on_tray_blocking_toggled(self, checked: bool) -> None:
        """Handle blocking toggle from tray menu."""
        self._store.set_blocking(checked)
        # Update the main window checkbox without triggering its handler
        self._blocking_checkbox.stateChanged.disconnect(self._on_blocking_changed)
        self._blocking_checkbox.setChecked(checked)
        self._blocking_checkbox.stateChanged.connect(self._on_blocking_changed)

    def _load_state(self) -> None:
        state = self._store.load()
        self._blocking_checkbox.setChecked(state.blocking)
        self._list.clear()
        for domain in state.domains:
            self._list.addItem(QListWidgetItem(domain))

    def _on_blocking_changed(self, state: int) -> None:
        blocking = state == Qt.CheckState.Checked.value
        self._store.set_blocking(blocking)
        # Sync tray menu checkbox
        if self._tray_blocking_action:
            self._tray_blocking_action.setChecked(blocking)

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

    def _set_blocking_state(self, blocking: bool) -> None:
        """Update the checkbox state from BLE without triggering the change handler.
        Enable checkbox when blocking=false, disable when blocking=true (phone in control)."""
        # Temporarily disconnect to avoid triggering _on_blocking_changed
        self._blocking_checkbox.stateChanged.disconnect(self._on_blocking_changed)
        self._blocking_checkbox.setChecked(blocking)
        # Disable checkbox when phone is actively blocking, enable when not
        self._blocking_checkbox.setEnabled(not blocking)
        self._blocking_checkbox.stateChanged.connect(self._on_blocking_changed)
        # Sync tray menu checkbox
        if self._tray_blocking_action:
            self._tray_blocking_action.setChecked(blocking)
        logger.info(f"Blocking state updated from BLE: {blocking}, checkbox {'disabled' if blocking else 'enabled'}")


def main() -> None:
    app = QApplication([])
    
    # Resolve icon path relative to repo root
    icon_path = Path(__file__).resolve().parents[2] / "Undistract-logo.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    # Keep app running when all windows are closed (tray mode)
    app.setQuitOnLastWindowClosed(False)
    
    window = MainWindow(icon_path)
    window.setup_tray_icon()
    window.resize(520, 480)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
