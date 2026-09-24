"""BackupDialog — detailed local backup status + manual-run UI.

No file/hash/network calls happen in this module; everything is delegated
through ``BackupController``/``BackupService``.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from shane_common.preferences import SettingsManager
from shane_common.watchdog.tray.base_window import BaseStatusWindow

from services.backup import state as backup_state
from services.backup import health as backup_health
from services.backup.catalog import PurityBackupCatalog
from services.backup.controller import BackupController
from services.backup.credentials import DropboxCredentialStore
from services.backup.dropbox_auth import DropboxAuthFlow, complete_authorization
from services.backup.dropbox_controller import DropboxController
from services.backup.dropbox_service import get_dropbox_auth_state
from services.backup.models import BackupRunResult, DropboxAuthState, RunStatus
from services.backup.recovery_drill import DROPBOX_NOT_CONFIGURED, DROPBOX_REAUTH_REQUIRED
from services.backup.recovery_drill_controller import RecoveryDrillController
from services.backup.restore import RestoreResult, load_restore_state
from services.backup.scheduler import load_schedule_state
from services.settings_schemas import (
    get_backup_local_destination,
    get_backup_recovery_drill_interval_days,
    get_backup_schedule_enabled,
    get_backup_schedule_time,
    get_backup_schedule_weekday,
    get_backup_selected_families,
    get_dropbox_app_key,
    get_dropbox_backup_enabled,
    get_dropbox_remote_folder,
    resolve_purity_data_root,
    set_backup_selected_families,
    set_dropbox_auth_invalid,
)

_WEEKDAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _family_label(name: str) -> str:
    return name.replace("_", " ").title()


class _FamilyPickerDialog(QtWidgets.QDialog):
    """Lists the Protected Data families (from the backup catalog) as checkboxes.

    Source file/folder paths for each family are already resolved by
    ``PurityBackupCatalog`` — this dialog only selects which families to
    include; the destination is configured separately (see
    ``BackupDialog._on_choose_destination_clicked``).
    """

    def __init__(
        self,
        catalog: PurityBackupCatalog,
        parent: QtWidgets.QWidget | None = None,
        *,
        preselected: set[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose Protected Data To Back Up")
        self._checkboxes: list[tuple[QtWidgets.QCheckBox, str]] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Select which protected data to back up:"))

        for family in catalog.discover():
            checkbox = QtWidgets.QCheckBox(_family_label(family.name))
            checkbox.setChecked(not preselected or family.name in preselected)
            layout.addWidget(checkbox)
            self._checkboxes.append((checkbox, family.name))

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText("Backup")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_families(self) -> set[str]:
        return {name for checkbox, name in self._checkboxes if checkbox.isChecked()}


class BackupDialog(BaseStatusWindow):
    def __init__(
        self,
        controller: BackupController,
        settings_manager: SettingsManager,
        parent: QtWidgets.QWidget | None = None,
        *,
        dropbox_controller: DropboxController | None = None,
        recovery_drill_controller: RecoveryDrillController | None = None,
    ) -> None:
        self._controller = controller
        self._settings_manager = settings_manager
        self._dropbox_controller = dropbox_controller
        self._recovery_drill_controller = recovery_drill_controller
        self._credential_store = DropboxCredentialStore()
        self._catalog = PurityBackupCatalog(settings_manager=settings_manager)
        self._families_label: QtWidgets.QLabel | None = None
        self._destination_icon_label: QtWidgets.QLabel | None = None
        self._destination_label: QtWidgets.QLabel | None = None
        self._last_run_label: QtWidgets.QLabel | None = None
        self._back_up_now_btn: QtWidgets.QPushButton | None = None
        self._schedule_enabled_checkbox: QtWidgets.QCheckBox | None = None
        self._schedule_weekday_combo: QtWidgets.QComboBox | None = None
        self._schedule_time_edit: QtWidgets.QTimeEdit | None = None
        self._next_run_label: QtWidgets.QLabel | None = None
        self._dropbox_enabled_checkbox: QtWidgets.QCheckBox | None = None
        self._dropbox_app_key_edit: QtWidgets.QLineEdit | None = None
        self._dropbox_remote_folder_edit: QtWidgets.QLineEdit | None = None
        self._dropbox_status_label: QtWidgets.QLabel | None = None
        self._dropbox_last_run_label: QtWidgets.QLabel | None = None
        self._dropbox_connect_btn: QtWidgets.QPushButton | None = None
        self._dropbox_disconnect_btn: QtWidgets.QPushButton | None = None
        self._dropbox_back_up_now_btn: QtWidgets.QPushButton | None = None
        self._recovery_local_label: QtWidgets.QLabel | None = None
        self._recovery_dropbox_label: QtWidgets.QLabel | None = None
        self._recovery_drill_btn: QtWidgets.QPushButton | None = None
        super().__init__(
            settings_org="purity",
            settings_app="PurityMonitor",
            title="Purity — Backup",
            parent=parent,
        )
        self._controller.run_started.connect(self._on_run_started)
        self._controller.run_finished.connect(self._on_run_finished)
        self._controller.run_rejected.connect(self._on_run_rejected)
        if self._dropbox_controller is not None:
            self._dropbox_controller.run_started.connect(self._on_dropbox_run_started)
            self._dropbox_controller.run_finished.connect(self._on_dropbox_run_finished)
            self._dropbox_controller.run_rejected.connect(self._on_dropbox_run_rejected)
        if self._recovery_drill_controller is not None:
            self._recovery_drill_controller.drill_started.connect(self._on_drill_started)
            self._recovery_drill_controller.drill_finished.connect(self._on_drill_finished)
            self._recovery_drill_controller.drill_rejected.connect(self._on_drill_rejected)
        self.refresh_requested.connect(self.refresh)

    def _build_content(self, container: QtWidgets.QWidget) -> None:
        layout = container.layout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        families_box = QtWidgets.QGroupBox("Protected Data")
        families_layout = QtWidgets.QVBoxLayout(families_box)
        self._families_label = QtWidgets.QLabel("—")
        self._families_label.setWordWrap(True)
        families_layout.addWidget(self._families_label)
        choose_families_btn = QtWidgets.QPushButton("Choose Protected Data...")
        choose_families_btn.clicked.connect(self._on_choose_protected_data_clicked)
        families_buttons_row = QtWidgets.QHBoxLayout()
        families_buttons_row.addWidget(choose_families_btn)
        families_buttons_row.addStretch()
        families_layout.addLayout(families_buttons_row)
        layout.addWidget(families_box)

        status_box = QtWidgets.QGroupBox("Local Backup")
        status_layout = QtWidgets.QVBoxLayout(status_box)
        dest_row = QtWidgets.QHBoxLayout()
        self._destination_icon_label = QtWidgets.QLabel()
        self._destination_icon_label.setFixedWidth(16)
        self._destination_label = QtWidgets.QLabel("—")
        dest_row.addWidget(self._destination_icon_label)
        dest_row.addWidget(self._destination_label, stretch=1)
        self._last_run_label = QtWidgets.QLabel("—")
        self._last_run_label.setWordWrap(True)
        status_layout.addLayout(dest_row)
        status_layout.addWidget(self._last_run_label)

        buttons_row = QtWidgets.QHBoxLayout()
        self._back_up_now_btn = QtWidgets.QPushButton("Back Up Now")
        self._back_up_now_btn.clicked.connect(self._on_back_up_now_clicked)
        choose_dest_btn = QtWidgets.QPushButton("Choose Local Destination...")
        choose_dest_btn.clicked.connect(self._on_choose_destination_clicked)
        buttons_row.addWidget(self._back_up_now_btn)
        buttons_row.addWidget(choose_dest_btn)
        buttons_row.addStretch()
        status_layout.addLayout(buttons_row)
        layout.addWidget(status_box)

        schedule_box = QtWidgets.QGroupBox("Weekly Schedule")
        schedule_layout = QtWidgets.QVBoxLayout(schedule_box)
        self._schedule_enabled_checkbox = QtWidgets.QCheckBox("Enable weekly backup")
        self._schedule_enabled_checkbox.toggled.connect(self._on_schedule_changed)
        schedule_layout.addWidget(self._schedule_enabled_checkbox)

        schedule_row = QtWidgets.QHBoxLayout()
        self._schedule_weekday_combo = QtWidgets.QComboBox()
        self._schedule_weekday_combo.addItems(_WEEKDAY_LABELS)
        self._schedule_weekday_combo.currentIndexChanged.connect(self._on_schedule_changed)
        self._schedule_time_edit = QtWidgets.QTimeEdit()
        self._schedule_time_edit.setDisplayFormat("HH:mm")
        self._schedule_time_edit.timeChanged.connect(self._on_schedule_changed)
        schedule_row.addWidget(self._schedule_weekday_combo)
        schedule_row.addWidget(self._schedule_time_edit)
        schedule_row.addStretch()
        schedule_layout.addLayout(schedule_row)

        self._next_run_label = QtWidgets.QLabel("—")
        self._next_run_label.setWordWrap(True)
        schedule_layout.addWidget(self._next_run_label)
        layout.addWidget(schedule_box)

        if self._dropbox_controller is not None:
            dropbox_box = QtWidgets.QGroupBox("Dropbox Backup")
            dropbox_layout = QtWidgets.QVBoxLayout(dropbox_box)

            self._dropbox_enabled_checkbox = QtWidgets.QCheckBox("Enable Dropbox backup")
            self._dropbox_enabled_checkbox.toggled.connect(self._on_dropbox_enabled_toggled)
            dropbox_layout.addWidget(self._dropbox_enabled_checkbox)

            key_row = QtWidgets.QHBoxLayout()
            key_row.addWidget(QtWidgets.QLabel("App key:"))
            self._dropbox_app_key_edit = QtWidgets.QLineEdit()
            self._dropbox_app_key_edit.textChanged.connect(self._on_dropbox_app_key_changed)
            key_row.addWidget(self._dropbox_app_key_edit)
            dropbox_layout.addLayout(key_row)

            folder_row = QtWidgets.QHBoxLayout()
            folder_row.addWidget(QtWidgets.QLabel("Remote folder:"))
            self._dropbox_remote_folder_edit = QtWidgets.QLineEdit()
            self._dropbox_remote_folder_edit.textChanged.connect(self._on_dropbox_remote_folder_changed)
            folder_row.addWidget(self._dropbox_remote_folder_edit)
            dropbox_layout.addLayout(folder_row)

            self._dropbox_status_label = QtWidgets.QLabel("—")
            self._dropbox_last_run_label = QtWidgets.QLabel("—")
            self._dropbox_last_run_label.setWordWrap(True)
            dropbox_layout.addWidget(self._dropbox_status_label)
            dropbox_layout.addWidget(self._dropbox_last_run_label)

            dropbox_buttons_row = QtWidgets.QHBoxLayout()
            self._dropbox_connect_btn = QtWidgets.QPushButton("Connect to Dropbox...")
            self._dropbox_connect_btn.clicked.connect(self._on_dropbox_connect_clicked)
            self._dropbox_disconnect_btn = QtWidgets.QPushButton("Disconnect")
            self._dropbox_disconnect_btn.clicked.connect(self._on_dropbox_disconnect_clicked)
            self._dropbox_back_up_now_btn = QtWidgets.QPushButton("Back Up to Dropbox Now")
            self._dropbox_back_up_now_btn.clicked.connect(self._on_dropbox_back_up_now_clicked)
            dropbox_buttons_row.addWidget(self._dropbox_connect_btn)
            dropbox_buttons_row.addWidget(self._dropbox_disconnect_btn)
            dropbox_buttons_row.addWidget(self._dropbox_back_up_now_btn)
            dropbox_buttons_row.addStretch()
            dropbox_layout.addLayout(dropbox_buttons_row)
            layout.addWidget(dropbox_box)

        if self._recovery_drill_controller is not None:
            recovery_box = QtWidgets.QGroupBox("Disaster Recovery")
            recovery_layout = QtWidgets.QVBoxLayout(recovery_box)

            self._recovery_local_label = QtWidgets.QLabel("—")
            self._recovery_dropbox_label = QtWidgets.QLabel("—")
            recovery_layout.addWidget(self._recovery_local_label)
            recovery_layout.addWidget(self._recovery_dropbox_label)

            interval = get_backup_recovery_drill_interval_days(self._settings_manager)
            recovery_layout.addWidget(
                QtWidgets.QLabel(f"Recommended every {interval} days.")
            )

            self._recovery_drill_btn = QtWidgets.QPushButton("Run Recovery Drill")
            self._recovery_drill_btn.clicked.connect(self._on_run_recovery_drill_clicked)
            recovery_buttons_row = QtWidgets.QHBoxLayout()
            recovery_buttons_row.addWidget(self._recovery_drill_btn)
            recovery_buttons_row.addStretch()
            recovery_layout.addLayout(recovery_buttons_row)
            layout.addWidget(recovery_box)

        self.refresh()

    def refresh(self) -> None:
        """Update the display from disk state."""
        destination_configured = get_backup_local_destination(self._settings_manager) is not None

        if self._families_label is not None:
            families = self._catalog.discover()
            selected = get_backup_selected_families(self._settings_manager)
            parts = [
                f"{'✓' if not selected or f.name in selected else '✗'} {_family_label(f.name)}"
                for f in families
            ]
            self._families_label.setText("\n".join(parts) or "(none found)")

        if self._destination_label is not None:
            destination = get_backup_local_destination(self._settings_manager)
            self._destination_label.setText(
                f"Destination: {destination}" if destination else "Destination: (not configured)"
            )
        if self._destination_icon_label is not None:
            if destination_configured:
                self._destination_icon_label.setPixmap(QtGui.QPixmap())
            else:
                icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical)
                self._destination_icon_label.setPixmap(icon.pixmap(16, 16))

        if self._last_run_label is not None:
            self._last_run_label.setText(self._format_last_run())
        if self._back_up_now_btn is not None:
            self._back_up_now_btn.setEnabled(destination_configured)

        self._refresh_schedule_controls(destination_configured)
        self._refresh_dropbox_controls(destination_configured)
        self._refresh_recovery_drill_controls()

    def _refresh_schedule_controls(self, destination_configured: bool) -> None:
        if (
            self._schedule_enabled_checkbox is None
            or self._schedule_weekday_combo is None
            or self._schedule_time_edit is None
        ):
            return
        self._schedule_enabled_checkbox.setEnabled(destination_configured)
        self._schedule_weekday_combo.setEnabled(destination_configured)
        self._schedule_time_edit.setEnabled(destination_configured)
        enabled = get_backup_schedule_enabled(self._settings_manager)
        weekday = get_backup_schedule_weekday(self._settings_manager)
        hour, minute = (2, 0)
        raw_time = get_backup_schedule_time(self._settings_manager)
        try:
            hour, minute = (int(part) for part in raw_time.split(":", 1))
        except (TypeError, ValueError):
            pass

        for widget in (
            self._schedule_enabled_checkbox,
            self._schedule_weekday_combo,
            self._schedule_time_edit,
        ):
            widget.blockSignals(True)
        self._schedule_enabled_checkbox.setChecked(enabled)
        self._schedule_weekday_combo.setCurrentIndex(max(0, min(6, weekday)))
        self._schedule_time_edit.setTime(QtCore.QTime(hour, minute))
        for widget in (
            self._schedule_enabled_checkbox,
            self._schedule_weekday_combo,
            self._schedule_time_edit,
        ):
            widget.blockSignals(False)

        if self._next_run_label is not None:
            self._next_run_label.setText(self._format_schedule_state())

    def _format_schedule_state(self) -> str:
        data_root = resolve_purity_data_root(self._settings_manager)
        state = load_schedule_state(data_root)
        if not state.last_evaluated_occurrence_id:
            return "No scheduled run yet."
        text = f"Last scheduled occurrence: {state.last_evaluated_occurrence_id}"
        if state.last_run_result_ref:
            text += f" (run {state.last_run_result_ref})"
        return text

    def _on_schedule_changed(self, *_args) -> None:
        if (
            self._schedule_enabled_checkbox is None
            or self._schedule_weekday_combo is None
            or self._schedule_time_edit is None
        ):
            return
        self._settings_manager.set(
            "app.general", "backup_schedule_enabled", self._schedule_enabled_checkbox.isChecked()
        )
        self._settings_manager.set(
            "app.general", "backup_schedule_weekday", self._schedule_weekday_combo.currentIndex()
        )
        self._settings_manager.set(
            "app.general",
            "backup_schedule_time",
            self._schedule_time_edit.time().toString("HH:mm"),
        )
        self._settings_manager.save()

    def _format_last_run(self) -> str:
        data_root = resolve_purity_data_root(self._settings_manager)
        runs = backup_state.load_state(data_root)
        if not runs:
            return "Last run: none yet"
        last = runs[-1]
        return (
            f"Last run: {last.status.value.upper()} at {last.completed_at or last.started_at} — "
            f"{last.verified_count}/{last.file_count} verified"
            + (f" ({last.failed_count} failed)" if last.failed_count else "")
        )

    def _on_choose_destination_clicked(self) -> None:
        chosen = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose Local Backup Destination")
        if not chosen:
            self.statusBar().showMessage("Choose Local Destination cancelled.")
            return
        self._settings_manager.set("app.general", "backup_local_destination", chosen)
        self._settings_manager.save()
        self.refresh()
        self.statusBar().showMessage(f"Local backup destination set to {chosen}")

    def _on_choose_protected_data_clicked(self) -> None:
        preselected = get_backup_selected_families(self._settings_manager)
        picker = _FamilyPickerDialog(self._catalog, self, preselected=preselected or None)
        if picker.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Choose Protected Data cancelled.")
            return
        families = picker.selected_families()
        if not families:
            self.statusBar().showMessage("At least one protected data item must be selected.")
            return
        set_backup_selected_families(self._settings_manager, families)
        self.refresh()
        self.statusBar().showMessage(f"Protected data selection updated: {len(families)} selected.")

    def _on_back_up_now_clicked(self) -> None:
        if not get_backup_local_destination(self._settings_manager):
            self.statusBar().showMessage("Choose a local backup destination first.")
            return
        families = get_backup_selected_families(self._settings_manager) or None
        if not self._controller.back_up_now(families):
            return
        if self._back_up_now_btn is not None:
            self._back_up_now_btn.setEnabled(False)

    def _on_run_started(self) -> None:
        if self._back_up_now_btn is not None:
            self._back_up_now_btn.setEnabled(False)
        if self._last_run_label is not None:
            self._last_run_label.setText("Backup running...")
        self.statusBar().showMessage("Local backup running...")

    def _on_run_finished(self, result: BackupRunResult) -> None:
        if self._back_up_now_btn is not None:
            self._back_up_now_btn.setEnabled(True)
        self.refresh()
        if result.status == RunStatus.SUCCESS:
            self.statusBar().showMessage("Local Backup SUCCESS!")
        else:
            self.statusBar().showMessage("Local Backup FAILED")
            print(f"Local backup failed: {result.last_error}")

    def _on_run_rejected(self, reason: str) -> None:
        if self._back_up_now_btn is not None:
            self._back_up_now_btn.setEnabled(True)
        self.statusBar().showMessage(f"Local Backup rejected: {reason}")
        QtWidgets.QMessageBox.information(self, "Backup", reason)

    # -- Dropbox ---------------------------------------------------------

    def _refresh_dropbox_controls(self, destination_configured: bool = True) -> None:
        if self._dropbox_controller is None:
            return

        enabled = get_dropbox_backup_enabled(self._settings_manager)
        if self._dropbox_enabled_checkbox is not None:
            self._dropbox_enabled_checkbox.blockSignals(True)
            self._dropbox_enabled_checkbox.setChecked(enabled)
            self._dropbox_enabled_checkbox.blockSignals(False)
        if self._dropbox_app_key_edit is not None and not self._dropbox_app_key_edit.hasFocus():
            self._dropbox_app_key_edit.setText(get_dropbox_app_key(self._settings_manager))
        if self._dropbox_remote_folder_edit is not None and not self._dropbox_remote_folder_edit.hasFocus():
            self._dropbox_remote_folder_edit.setText(get_dropbox_remote_folder(self._settings_manager))

        auth_state = get_dropbox_auth_state(self._settings_manager, self._credential_store)
        if self._dropbox_status_label is not None:
            status_text = self._describe_dropbox_state(auth_state)
            if not destination_configured:
                status_text += " — local backup destination not configured"
            self._dropbox_status_label.setText(f"Status: {status_text}")
        if self._dropbox_connect_btn is not None:
            self._dropbox_connect_btn.setEnabled(destination_configured)
        if self._dropbox_disconnect_btn is not None:
            self._dropbox_disconnect_btn.setEnabled(destination_configured and auth_state == DropboxAuthState.READY)
        if self._dropbox_back_up_now_btn is not None:
            self._dropbox_back_up_now_btn.setEnabled(destination_configured and auth_state == DropboxAuthState.READY)
        if self._dropbox_last_run_label is not None:
            self._dropbox_last_run_label.setText(self._format_dropbox_last_run())

    def _describe_dropbox_state(self, auth_state: DropboxAuthState) -> str:
        if auth_state == DropboxAuthState.READY:
            return "connected and ready"
        if auth_state == DropboxAuthState.REAUTH_REQUIRED:
            return "credential rejected — click Connect to Dropbox... to reauthorize"
        if auth_state == DropboxAuthState.AUTH_REQUIRED:
            if not get_dropbox_app_key(self._settings_manager):
                return "not connected — enter an app key, then click Connect to Dropbox..."
            return "not connected — click Connect to Dropbox..."
        return "disabled — click Connect to Dropbox... to enable and connect"

    def _format_dropbox_last_run(self) -> str:
        data_root = resolve_purity_data_root(self._settings_manager)
        runs = backup_state.load_dropbox_state(data_root)
        if not runs:
            return "Last Dropbox run: none yet"
        last = runs[-1]
        return (
            f"Last Dropbox run: {last.status.value.upper()} at {last.completed_at or last.started_at} — "
            f"{last.verified_count}/{last.file_count} verified"
            + (f" ({last.failed_count} failed)" if last.failed_count else "")
        )

    def _on_dropbox_enabled_toggled(self, checked: bool) -> None:
        self._settings_manager.set("app.general", "dropbox_backup_enabled", checked)
        self._settings_manager.save()
        self.refresh()
        self.statusBar().showMessage(f"Dropbox backup {'enabled' if checked else 'disabled'}.")

    def _on_dropbox_app_key_changed(self, *_args) -> None:
        if self._dropbox_app_key_edit is None:
            return
        self._settings_manager.set("app.general", "dropbox_app_key", self._dropbox_app_key_edit.text().strip())
        self._settings_manager.save()
        self._refresh_dropbox_controls()

    def _on_dropbox_remote_folder_changed(self, *_args) -> None:
        if self._dropbox_remote_folder_edit is None:
            return
        self._settings_manager.set(
            "app.general", "dropbox_remote_folder", self._dropbox_remote_folder_edit.text().strip()
        )
        self._settings_manager.save()

    def _on_dropbox_connect_clicked(self) -> None:
        app_key = get_dropbox_app_key(self._settings_manager)
        if not app_key:
            QtWidgets.QMessageBox.information(self, "Dropbox", "Enter an app key first.")
            return

        try:
            flow = DropboxAuthFlow(app_key)
            authorize_url = flow.start()
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            self.statusBar().showMessage(f"Dropbox authorization failed to start: {exc}")
            QtWidgets.QMessageBox.warning(self, "Dropbox", f"Could not start authorization: {exc}")
            return

        QtGui.QDesktopServices.openUrl(QtCore.QUrl(authorize_url))
        auth_code, ok = QtWidgets.QInputDialog.getText(
            self,
            "Dropbox",
            "A browser window opened for you to approve access.\n"
            "Paste the authorization code Dropbox gave you:",
        )
        if not ok or not auth_code.strip():
            return

        try:
            complete_authorization(
                app_key,
                auth_code,
                flow=flow,
                credential_store=self._credential_store,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            self.statusBar().showMessage(f"Dropbox authorization failed: {exc}")
            QtWidgets.QMessageBox.warning(self, "Dropbox", f"Authorization failed: {exc}")
            return

        self._settings_manager.set("app.general", "dropbox_backup_enabled", True)
        self._settings_manager.save()
        set_dropbox_auth_invalid(self._settings_manager, False)
        self.refresh()
        self.statusBar().showMessage("Dropbox connected successfully.")
        QtWidgets.QMessageBox.information(self, "Dropbox", "Dropbox connected successfully.")

    def _on_dropbox_disconnect_clicked(self) -> None:
        answer = QtWidgets.QMessageBox.question(
            self,
            "Dropbox",
            "Disconnect Dropbox and remove the stored credential?",
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage("Dropbox disconnect cancelled.")
            return
        self._credential_store.clear_all()
        self._settings_manager.set("app.general", "dropbox_backup_enabled", False)
        self._settings_manager.save()
        set_dropbox_auth_invalid(self._settings_manager, False)
        self.refresh()
        self.statusBar().showMessage("Dropbox disconnected.")

    def _on_dropbox_back_up_now_clicked(self) -> None:
        if self._dropbox_controller is None or not self._dropbox_controller.back_up_now():
            return
        if self._dropbox_back_up_now_btn is not None:
            self._dropbox_back_up_now_btn.setEnabled(False)

    def _on_dropbox_run_started(self) -> None:
        if self._dropbox_back_up_now_btn is not None:
            self._dropbox_back_up_now_btn.setEnabled(False)
        if self._dropbox_last_run_label is not None:
            self._dropbox_last_run_label.setText("Dropbox backup running...")
        self.statusBar().showMessage("Dropbox backup running...")

    def _on_dropbox_run_finished(self, result: BackupRunResult) -> None:
        self.refresh()
        if result.status == RunStatus.SUCCESS:
            self.statusBar().showMessage("Dropbox Backup SUCCESS!")
        else:
            self.statusBar().showMessage(f"Dropbox Backup {result.status.value.upper()}")
        if result.status != RunStatus.SUCCESS:
            QtWidgets.QMessageBox.warning(
                self,
                "Dropbox Backup",
                f"Dropbox backup completed with status {result.status.value.upper()}."
                + (f"\n{result.last_error}" if result.last_error else ""),
            )

    def _on_dropbox_run_rejected(self, reason: str) -> None:
        self.refresh()
        self.statusBar().showMessage(f"Dropbox Backup rejected: {reason}")
        QtWidgets.QMessageBox.information(self, "Dropbox Backup", reason)

    # -- Disaster Recovery -------------------------------------------------

    def _format_recovery_label(self, destination_name: str, destination_key: str) -> str:
        data_root = resolve_purity_data_root(self._settings_manager)
        interval = get_backup_recovery_drill_interval_days(self._settings_manager)
        runs = load_restore_state(data_root)
        last = backup_health.last_successful_restore(runs, destination_key)
        if last is None:
            return f"{destination_name}\nLast recovery drill: never \u26a0 DUE"
        due = backup_health.is_recovery_drill_due(last.get("completed_at"), interval_days=interval)
        when = last.get("completed_at") or last.get("started_at") or "unknown"
        marker = "\u26a0 DUE" if due else "\u2713"
        return f"{destination_name}\nLast recovery drill: {when}  {marker}"

    def _refresh_recovery_drill_controls(self) -> None:
        if self._recovery_drill_controller is None:
            return
        if self._recovery_local_label is not None:
            self._recovery_local_label.setText(self._format_recovery_label("Local backup", "local"))
        if self._recovery_dropbox_label is not None:
            auth_state = get_dropbox_auth_state(self._settings_manager, self._credential_store)
            if auth_state == DropboxAuthState.DISABLED or auth_state == DropboxAuthState.AUTH_REQUIRED:
                self._recovery_dropbox_label.setText("Dropbox\nNot configured")
            elif auth_state == DropboxAuthState.REAUTH_REQUIRED:
                self._recovery_dropbox_label.setText("Dropbox\nReauthentication required")
            else:
                self._recovery_dropbox_label.setText(self._format_recovery_label("Dropbox", "dropbox"))
        if self._recovery_drill_btn is not None:
            self._recovery_drill_btn.setEnabled(not self._recovery_drill_controller.is_running)

    def _on_run_recovery_drill_clicked(self) -> None:
        if self._recovery_drill_controller is None or not self._recovery_drill_controller.run_drill():
            return
        if self._recovery_drill_btn is not None:
            self._recovery_drill_btn.setEnabled(False)

    def _on_drill_started(self) -> None:
        if self._recovery_drill_btn is not None:
            self._recovery_drill_btn.setEnabled(False)
        if self._recovery_local_label is not None:
            self._recovery_local_label.setText("Local backup\nRunning...")
        if self._recovery_dropbox_label is not None:
            self._recovery_dropbox_label.setText("Dropbox\nRunning...")
        self.statusBar().showMessage("Recovery drill running...")

    def _on_drill_finished(self, results: dict) -> None:
        self.refresh()
        local_result = results.get("local")
        dropbox_result = results.get("dropbox")
        messages = []
        if isinstance(local_result, RestoreResult):
            messages.append(f"LOCAL: {local_result.status.upper()}")
        if isinstance(dropbox_result, RestoreResult):
            messages.append(f"DROPBOX: {dropbox_result.status.upper()}")
        elif dropbox_result == DROPBOX_NOT_CONFIGURED:
            messages.append("DROPBOX: not configured")
        elif dropbox_result == DROPBOX_REAUTH_REQUIRED:
            messages.append("DROPBOX: reauthentication required")
        self.statusBar().showMessage("Recovery drill finished — " + "; ".join(messages))

    def _on_drill_rejected(self, reason: str) -> None:
        self.refresh()
        self.statusBar().showMessage(f"Recovery drill rejected: {reason}")
        QtWidgets.QMessageBox.information(self, "Disaster Recovery", reason)
