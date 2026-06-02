"""
PurityTrayApp — system tray icon + polling loop for purity_app.

Uses BaseTrayApp from shane_common.watchdog.tray so the quit audit and
liveness machinery are shared across all supervised applications.

Tray icon colour:
  Green  — purity_app heartbeat fresh
  Yellow — purity_app heartbeat stale
  Red    — purity_app heartbeat dead / never written
  Gray   — heartbeats directory not yet present

Left-click or double-click shows / hides the PurityStatusWindow.
Right-click: Show Status | ─── | Quit  (Quit is appended by BaseTrayApp.start()).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets
from PySide6.QtWidgets import QSystemTrayIcon

from shane_common.watchdog.audit import AppendOnlyAuditLog
from shane_common.watchdog.tray.base_tray_app import BaseTrayApp
from shane_common.watchdog.tray.base_window import BaseStatusWindow
from shane_common.watchdog.tray.icons import (
    COLOR_GRAY,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    make_circle_icon,
)

try:
    from purity_app.services.supervisor_client import PuritySupervisorClient
except ModuleNotFoundError:
    from services.supervisor_client import PuritySupervisorClient  # type: ignore[no-redef]


class PurityStatusWindow(BaseStatusWindow):
    """
    Simple status window for purity_app liveness.

    Shows the latest heartbeat age and the last few audit lines.
    """

    def __init__(self, client: PuritySupervisorClient, parent=None) -> None:
        super().__init__(
            settings_org="purity",
            settings_app="PurityMonitor",
            title="Purity — Status",
            parent=parent,
        )
        self._client = client
        self._status_label: Optional[QtWidgets.QLabel] = None

    def _build_content(self, container: QtWidgets.QWidget) -> None:
        layout = container.layout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._status_label = QtWidgets.QLabel("—")
        self._status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._status_label)
        layout.addStretch()

    def refresh(self) -> None:
        """Update the display from disk state."""
        if self._status_label is None:
            return
        reader = self._client.heartbeat_reader
        _, mtime, exit_present = reader.read("purity_app")
        if mtime is None:
            text = "purity_app: no heartbeat file"
        elif exit_present:
            text = "purity_app: EXPECTED_EXIT (exit marker present)"
        elif reader.is_dead(mtime):
            import time
            age = time.time() - mtime
            text = f"purity_app: DEAD ({age:.0f}s since last heartbeat)"
        elif reader.is_stale(mtime):
            import time
            age = time.time() - mtime
            text = f"purity_app: STALE ({age:.1f}s)"
        else:
            import time
            age = time.time() - mtime
            text = f"purity_app: HEALTHY ({age:.1f}s)"
        self._status_label.setText(text)


class PurityTrayApp(BaseTrayApp):
    """
    Tray icon for purity_app.

    Parameters
    ----------
    data_root:
        Root data directory.  Passed through to PuritySupervisorClient.
    """

    def __init__(
        self,
        data_root: Path,
        main_window: QtWidgets.QWidget | None = None,
        reload_fn=None,
        parent=None,
    ) -> None:
        self._client = PuritySupervisorClient(data_root)
        self._main_window = main_window
        self._reload_fn = reload_fn
        liveness_path = (
            data_root / "_system" / "purity" / "locks" / "purity_tray.liveness.json"
        )
        super().__init__(
            liveness_path=liveness_path,
            settings_org="purity",
            settings_app="PurityMonitor",
            parent=parent,
        )
        self._status_window = PurityStatusWindow(self._client)

        # Tray initial tooltip
        self._tray.setToolTip("Purity")

        # Context menu — Quit is appended by BaseTrayApp.start()
        show_main_action = self._menu.addAction("Show Purity")
        show_main_action.triggered.connect(self._show_main_window)
        show_status_action = self._menu.addAction("Show Status")
        show_status_action.triggered.connect(self._toggle_status_window)
        if self._reload_fn is not None:
            reload_action = self._menu.addAction("Reload")
            reload_action.triggered.connect(self._request_reload)
        self._menu.addSeparator()

    # ------------------------------------------------------------------
    # BaseTrayApp interface
    # ------------------------------------------------------------------

    @property
    def _app_id(self) -> str:
        return "purity_tray"

    @property
    def _audit_log(self) -> Optional[AppendOnlyAuditLog]:
        return self._client.audit_log

    def _poll(self) -> None:
        """Update tray icon colour from heartbeat freshness."""
        reader = self._client.heartbeat_reader
        _, mtime, exit_present = reader.read("purity_app")

        if mtime is None:
            color = COLOR_GRAY
            tip = "Purity: not running"
        elif exit_present:
            color = COLOR_GRAY
            tip = "Purity: stopped (expected exit)"
        elif reader.is_dead(mtime):
            color = COLOR_RED
            tip = "Purity: DEAD"
        elif reader.is_stale(mtime):
            color = COLOR_YELLOW
            tip = "Purity: STALE"
        else:
            color = COLOR_GREEN
            tip = "Purity: running"

        self._tray.setIcon(make_circle_icon(color))
        self._tray.setToolTip(tip)

        if self._status_window.isVisible():
            self._status_window.refresh()

    def _on_show_hide(self) -> None:
        if self._show_main_window():
            return

        self._toggle_status_window()

    def _show_main_window(self) -> bool:
        if self._main_window is None:
            return False

        if self._main_window.isMinimized():
            self._main_window.showNormal()
        else:
            self._main_window.show()
        self._main_window.raise_()
        self._main_window.activateWindow()
        return True

    def _toggle_status_window(self) -> None:
        if self._status_window.isVisible():
            self._status_window.hide()
        else:
            self._status_window.show_and_raise()

    def notify_running(self, message: str, *, title: str = "Purity") -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if not self._tray.supportsMessages():
            return
        self._tray.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    def _request_reload(self) -> None:
        if self._reload_fn is None:
            return
        self._reload_fn()
