"""
PurityTrayApp — system tray icon + polling loop for purity_app.

Uses BaseTrayApp from shane_common.watchdog.tray so the quit audit and
liveness machinery are shared across all supervised applications.

Tray icon is a static PNG (icons/icon_16x16.png); status is conveyed via tooltip:
  "running"  — purity_app heartbeat fresh
  "STALE"    — purity_app heartbeat stale
  "DEAD"     — purity_app heartbeat dead / never written
  "not running" — heartbeats directory not yet present

Left-click or double-click shows / hides the PurityStatusWindow.
Right-click: Show Status | ─── | Quit  (Quit is appended by BaseTrayApp.start()).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from shane_common.watchdog.audit import AppendOnlyAuditLog
from shane_common.watchdog.tray.base_tray_app import BaseTrayApp
from shane_common.watchdog.tray.base_window import BaseStatusWindow
from shane_common.watchdog.tray.icons import (
    COLOR_GRAY,
    COLOR_GREEN,
    COLOR_YELLOW,
)

try:
    from purity_app.services.backup import health as backup_health
    from purity_app.services.backup import state as backup_state
    from purity_app.services.backup.controller import BackupController
    from purity_app.services.backup.dropbox_controller import DropboxController
    from purity_app.services.backup.dropbox_service import get_dropbox_auth_state
    from purity_app.services.backup.models import RunStatus
    from purity_app.services.backup.recovery_drill import (
        DROPBOX_NOT_CONFIGURED,
        DROPBOX_REAUTH_REQUIRED,
    )
    from purity_app.services.backup.recovery_drill_controller import RecoveryDrillController
    from purity_app.services.backup.restore import load_restore_state
    from purity_app.services.browser_session import ExtensionHeartbeatMonitor
    from purity_app.services.settings_schemas import (
        get_backup_local_destination,
        get_backup_recovery_drill_interval_days,
        get_backup_stale_threshold_days,
        get_debug_mode_enabled,
        resolve_purity_data_root,
        set_debug_mode_enabled,
    )
    from purity_app.services.supervisor_client import PuritySupervisorClient
except ModuleNotFoundError:
    from services.backup import health as backup_health  # type: ignore[no-redef]
    from services.backup import state as backup_state  # type: ignore[no-redef]
    from services.backup.controller import BackupController  # type: ignore[no-redef]
    from services.backup.dropbox_controller import DropboxController  # type: ignore[no-redef]
    from services.backup.dropbox_service import get_dropbox_auth_state  # type: ignore[no-redef]
    from services.backup.models import RunStatus  # type: ignore[no-redef]
    from services.backup.recovery_drill import (  # type: ignore[no-redef]
        DROPBOX_NOT_CONFIGURED,
        DROPBOX_REAUTH_REQUIRED,
    )
    from services.backup.recovery_drill_controller import RecoveryDrillController  # type: ignore[no-redef]
    from services.backup.restore import load_restore_state  # type: ignore[no-redef]
    from services.browser_session import ExtensionHeartbeatMonitor  # type: ignore[no-redef]
    from services.settings_schemas import (  # type: ignore[no-redef]
        get_backup_local_destination,
        get_backup_recovery_drill_interval_days,
        get_backup_stale_threshold_days,
        get_debug_mode_enabled,
        resolve_purity_data_root,
        set_debug_mode_enabled,
    )
    from services.supervisor_client import PuritySupervisorClient  # type: ignore[no-redef]


class PurityStatusWindow(BaseStatusWindow):
    """
    Simple status window for purity_app liveness.

    Shows the latest heartbeat age and the last few audit lines.
    """

    def __init__(self, client: PuritySupervisorClient, settings_manager=None, parent=None) -> None:
        self._client = client
        self._settings_manager = settings_manager
        self._status_label: Optional[QtWidgets.QLabel] = None
        self._extension_status_label: Optional[QtWidgets.QLabel] = None
        self._backup_status_label: Optional[QtWidgets.QLabel] = None
        self._recovery_drill_status_label: Optional[QtWidgets.QLabel] = None
        self._extension_heartbeat_monitor = ExtensionHeartbeatMonitor(client.heartbeats_dir.parents[2])
        super().__init__(
            settings_org="purity",
            settings_app="PurityMonitor",
            title="Purity — Status",
            parent=parent,
        )

    def _build_content(self, container: QtWidgets.QWidget) -> None:
        layout = container.layout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._status_label = QtWidgets.QLabel("—")
        self._status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._status_label)

        self._extension_status_label = QtWidgets.QLabel("—")
        self._extension_status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._extension_status_label)

        self._backup_status_label = QtWidgets.QLabel("—")
        self._backup_status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._backup_status_label)

        self._recovery_drill_status_label = QtWidgets.QLabel("—")
        self._recovery_drill_status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._recovery_drill_status_label)
        layout.addStretch()

    def _set_extension_status_style(self, color: str) -> None:
        if self._extension_status_label is None:
            return
        self._extension_status_label.setStyleSheet(f"font-weight: 600; color: {color};")

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

        if self._extension_status_label is None:
            return

        extension_status = self._extension_heartbeat_monitor.get_status()
        if extension_status.get("healthy"):
            age_seconds = float(extension_status.get("age_seconds") or 0.0)
            version = str(extension_status.get("extension_version") or "unknown")
            extension_text = (
                f"extension heartbeat: HEALTHY ({age_seconds:.1f}s since last ping, v{version})"
            )
            extension_color = COLOR_GREEN
        elif extension_status.get("last_seen_ts") is not None:
            age_seconds = extension_status.get("age_seconds")
            age_text = "unknown age" if age_seconds is None else f"{float(age_seconds):.1f}s since last ping"
            extension_text = f"extension heartbeat: STALE ({age_text})"
            extension_color = COLOR_YELLOW
        else:
            extension_text = "extension heartbeat: no heartbeat received"
            extension_color = COLOR_GRAY
        self._extension_status_label.setText(extension_text)
        self._set_extension_status_style(extension_color)

        if self._backup_status_label is not None:
            self._backup_status_label.setText(self._format_backup_status())
        if self._recovery_drill_status_label is not None:
            self._recovery_drill_status_label.setText(self._format_recovery_drill_status())

    def _format_backup_status(self) -> str:
        if self._settings_manager is None:
            return "backup: unavailable"
        destination = get_backup_local_destination(self._settings_manager)
        data_root = resolve_purity_data_root(self._settings_manager)
        if destination is None:
            local_text = "LOCAL not configured"
        else:
            runs = backup_state.load_state(data_root)
            if not runs:
                local_text = "LOCAL configured, no runs yet"
            else:
                last = runs[-1]
                local_text = (
                    f"LOCAL {last.status.value.upper()} "
                    f"({last.verified_count}/{last.file_count} verified) at "
                    f"{last.completed_at or last.started_at}"
                )

        if destination is not None:
            threshold = get_backup_stale_threshold_days(self._settings_manager)
            if backup_health.is_stale(runs, threshold):
                local_text += " [STALE]"

        auth_state = get_dropbox_auth_state(self._settings_manager)
        dropbox_runs = backup_state.load_dropbox_state(data_root)
        if not dropbox_runs:
            dropbox_text = f"DROPBOX {auth_state.value}"
        else:
            last_dropbox = dropbox_runs[-1]
            dropbox_text = (
                f"DROPBOX {last_dropbox.status.value.upper()} "
                f"({last_dropbox.verified_count}/{last_dropbox.file_count} verified) at "
                f"{last_dropbox.completed_at or last_dropbox.started_at}"
            )
            threshold = get_backup_stale_threshold_days(self._settings_manager)
            if backup_health.is_stale(dropbox_runs, threshold):
                dropbox_text += " [STALE]"

        return f"backup: {local_text} | {dropbox_text}"

    def _format_recovery_drill_status(self) -> str:
        if self._settings_manager is None:
            return "recovery drill: unavailable"
        data_root = resolve_purity_data_root(self._settings_manager)
        interval = get_backup_recovery_drill_interval_days(self._settings_manager)
        runs = load_restore_state(data_root)

        local_last = backup_health.last_successful_restore(runs, "local")
        local_due = backup_health.is_recovery_drill_due(
            local_last.get("completed_at") if local_last else None, interval_days=interval
        )
        local_text = f"LOCAL {'due' if local_due else 'ok'}"

        dropbox_last = backup_health.last_successful_restore(runs, "dropbox")
        dropbox_due = backup_health.is_recovery_drill_due(
            dropbox_last.get("completed_at") if dropbox_last else None, interval_days=interval
        )
        dropbox_text = f"DROPBOX {'due' if dropbox_due else 'ok'}"

        return f"recovery drill: {local_text} | {dropbox_text}"


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
        panic_button: QtWidgets.QWidget | None = None,
        settings_manager=None,
        backup_controller: "BackupController | None" = None,
        dropbox_controller: "DropboxController | None" = None,
        recovery_drill_controller: "RecoveryDrillController | None" = None,
        parent=None,
    ) -> None:
        self._client = PuritySupervisorClient(data_root)
        self._main_window = main_window
        self._reload_fn = reload_fn
        self._panic_btn = panic_button
        self._settings_manager = settings_manager
        self._backup_controller = backup_controller
        self._dropbox_controller = dropbox_controller
        self._recovery_drill_controller = recovery_drill_controller
        self._backup_dialog = None
        self._local_backup_was_stale = False
        self._dropbox_backup_was_stale = False
        self._local_drill_was_due = False
        self._dropbox_drill_was_due = False
        liveness_path = (
            data_root / "_system" / "purity" / "locks" / "purity_tray.liveness.json"
        )
        super().__init__(
            liveness_path=liveness_path,
            settings_org="purity",
            settings_app="PurityMonitor",
            parent=parent,
        )
        self._status_window = PurityStatusWindow(self._client, settings_manager=settings_manager)
        if self._backup_controller is not None:
            self._backup_controller.run_finished.connect(
                lambda result: self._notify_backup_result("Local", result)
            )
        if self._dropbox_controller is not None:
            self._dropbox_controller.run_finished.connect(
                lambda result: self._notify_backup_result("Dropbox", result)
            )

        # Tray initial icon + tooltip
        self._tray.setIcon(QIcon(str(Path(__file__).parents[1] / "icons" / "icon_16x16.png")))
        self._tray.setToolTip("Purity")

        # Context menu — Quit is appended by BaseTrayApp.start()
        show_main_action = self._menu.addAction("Show Purity")
        show_main_action.triggered.connect(self._show_main_window)
        show_status_action = self._menu.addAction("Show Status")
        show_status_action.triggered.connect(self._toggle_status_window)
        if self._backup_controller is not None and self._settings_manager is not None:
            backup_action = self._menu.addAction("Backup...")
            backup_action.triggered.connect(self._toggle_backup_dialog)
        if self._reload_fn is not None:
            reload_action = self._menu.addAction("Reload")
            reload_action.triggered.connect(self._request_reload)
        self._debug_mode_action = None
        if self._reload_fn is not None and self._settings_manager is not None:
            self._debug_mode_action = self._menu.addAction(self._debug_mode_action_label())
            self._debug_mode_action.triggered.connect(self._toggle_debug_mode)
        self._panic_visible_action = None
        if self._panic_btn is not None:
            self._panic_visible_action = self._menu.addAction("Show Panic Button")
            self._panic_visible_action.setCheckable(True)
            self._panic_visible_action.setChecked(True)
            self._panic_visible_action.triggered.connect(self._toggle_panic_button)
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
        """Update tray tooltip from heartbeat freshness."""
        reader = self._client.heartbeat_reader
        _, mtime, exit_present = reader.read("purity_app")

        if mtime is None:
            tip = "Purity: not running"
        elif exit_present:
            tip = "Purity: stopped (expected exit)"
        elif reader.is_dead(mtime):
            tip = "Purity: DEAD"
        elif reader.is_stale(mtime):
            tip = "Purity: STALE"
        else:
            tip = "Purity: running"

        self._tray.setToolTip(tip)

        if self._status_window.isVisible():
            self._status_window.refresh()

        self._poll_backup_staleness()
        self._poll_recovery_drill_due()

    def _poll_backup_staleness(self) -> None:
        if self._settings_manager is None:
            return
        data_root = resolve_purity_data_root(self._settings_manager)
        threshold = get_backup_stale_threshold_days(self._settings_manager)

        destination = get_backup_local_destination(self._settings_manager)
        if destination is not None:
            stale = backup_health.is_stale(backup_state.load_state(data_root), threshold)
            if stale and not self._local_backup_was_stale:
                self.notify_running(
                    f"No successful local backup in over {threshold} day(s).",
                    title="Purity Backup",
                )
            self._local_backup_was_stale = stale

        if get_dropbox_auth_state(self._settings_manager).value == "ready":
            stale = backup_health.is_stale(backup_state.load_dropbox_state(data_root), threshold)
            if stale and not self._dropbox_backup_was_stale:
                self.notify_running(
                    f"No successful Dropbox backup in over {threshold} day(s).",
                    title="Purity Backup",
                )
            self._dropbox_backup_was_stale = stale

    def _poll_recovery_drill_due(self) -> None:
        """Reminds once when a recovery drill transitions healthy -> due.

        Follows the same low-noise philosophy as ``_poll_backup_staleness``:
        this is a passive reminder, not an automatic monthly drill — the user
        still initiates the drill via the "Run Recovery Drill" button.
        """
        if self._settings_manager is None:
            return
        data_root = resolve_purity_data_root(self._settings_manager)
        interval = get_backup_recovery_drill_interval_days(self._settings_manager)
        runs = load_restore_state(data_root)

        local_due = False
        if get_backup_local_destination(self._settings_manager) is not None:
            last = backup_health.last_successful_restore(runs, "local")
            local_due = backup_health.is_recovery_drill_due(
                last.get("completed_at") if last else None, interval_days=interval
            )
        local_transitioned = local_due and not self._local_drill_was_due
        self._local_drill_was_due = local_due

        dropbox_due = False
        if get_dropbox_auth_state(self._settings_manager).value == "ready":
            last = backup_health.last_successful_restore(runs, "dropbox")
            dropbox_due = backup_health.is_recovery_drill_due(
                last.get("completed_at") if last else None, interval_days=interval
            )
        dropbox_transitioned = dropbox_due and not self._dropbox_drill_was_due
        self._dropbox_drill_was_due = dropbox_due

        if local_transitioned and dropbox_transitioned:
            self.notify_running(
                f"LOCAL and Dropbox backups have not been recovery-verified within the last "
                f"{interval} days.\n\nOpen Backup to run the drill.",
                title="Disaster Recovery Drill Due",
            )
        elif local_transitioned:
            self.notify_running(
                f"Your local backup has not been recovery-verified within the last {interval} "
                f"days.\n\nOpen Backup to run the drill.",
                title="Disaster Recovery Drill Due",
            )
        elif dropbox_transitioned:
            self.notify_running(
                f"Your Dropbox backup has not been recovery-verified within the last {interval} "
                f"days.\n\nOpen Backup to run the drill.",
                title="Disaster Recovery Drill Due",
            )

    def _notify_backup_result(self, label: str, result) -> None:
        if result.status == RunStatus.SUCCESS:
            return
        self.notify_running(
            f"{label} backup {result.status.value.upper()}: {result.last_error or 'see Backup dialog for details'}",
            title="Purity Backup",
        )

    def _save_prefs(self) -> None:
        if self._panic_visible_action is None:
            return
        s = self._settings()
        s.setValue("panic_button/visible", self._panic_visible_action.isChecked())
        s.sync()

    def _restore_prefs(self) -> None:
        if self._panic_btn is None or self._panic_visible_action is None:
            return
        s = self._settings()
        visible = s.value("panic_button/visible", True, type=bool)
        self._panic_visible_action.setChecked(visible)
        if visible:
            self._panic_btn.show()
        else:
            self._panic_btn.hide()

    def _toggle_panic_button(self) -> None:
        if self._panic_btn is None or self._panic_visible_action is None:
            return
        if self._panic_visible_action.isChecked():
            self._panic_btn.show()
        else:
            self._panic_btn.hide()

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

    def _toggle_backup_dialog(self) -> None:
        if self._backup_controller is None or self._settings_manager is None:
            return
        if self._backup_dialog is None:
            from ui.backup.backup_dialog import BackupDialog

            self._backup_dialog = BackupDialog(
                self._backup_controller,
                self._settings_manager,
                dropbox_controller=self._dropbox_controller,
                recovery_drill_controller=self._recovery_drill_controller,
            )
        if self._backup_dialog.isVisible():
            self._backup_dialog.hide()
        else:
            self._backup_dialog.show_and_raise()

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

    def _debug_mode_action_label(self) -> str:
        if get_debug_mode_enabled(self._settings_manager):
            return "Relaunch in Live"
        return "Relaunch in Debug"

    def _toggle_debug_mode(self) -> None:
        if self._settings_manager is None or self._reload_fn is None:
            return
        set_debug_mode_enabled(self._settings_manager, not get_debug_mode_enabled(self._settings_manager))
        if self._debug_mode_action is not None:
            self._debug_mode_action.setText(self._debug_mode_action_label())
        self._reload_fn()
