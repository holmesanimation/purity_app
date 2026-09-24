"""DropboxController — Qt glue between UI (tray/dialog) and DropboxBackupService.

Mirrors ``BackupController`` but owns its own single-flight lock, independent
of the local backup lock: a Dropbox run and a local run may proceed
concurrently (both only read source files), while overlapping Dropbox runs
are still prevented.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from shane_common.preferences import SettingsManager

from .dropbox_service import DropboxBackupService, get_dropbox_auth_state
from .lock import SingleFlightLock
from .models import BackupRunResult, DropboxAuthState


class DropboxController(QObject):
    run_started = Signal()
    run_finished = Signal(object)  # BackupRunResult
    run_rejected = Signal(str)  # human-readable reason

    def __init__(self, settings_manager: SettingsManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager
        self._service = DropboxBackupService(settings_manager=settings_manager)
        self._lock = SingleFlightLock()
        self._thread: QThread | None = None
        self._worker: "_DropboxWorker | None" = None

    @property
    def is_running(self) -> bool:
        return self._lock.locked

    def back_up_now(self) -> bool:
        """Start a Dropbox backup run in the background. Returns False if rejected."""
        auth_state = get_dropbox_auth_state(self._settings_manager)
        if auth_state != DropboxAuthState.READY:
            self.run_rejected.emit(f"Dropbox is not ready ({auth_state.value}).")
            return False
        if not self._lock.try_acquire():
            self.run_rejected.emit("A Dropbox backup run is already in progress.")
            return False

        self._thread = QThread(self)
        self._worker = _DropboxWorker(self._service)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self.run_started.emit()
        self._thread.start()
        return True

    @Slot(object)
    def _on_finished(self, result: BackupRunResult) -> None:
        self._lock.release()
        self.run_finished.emit(result)


class _DropboxWorker(QObject):
    finished = Signal(object)  # BackupRunResult

    def __init__(self, service: DropboxBackupService) -> None:
        super().__init__()
        self._service = service

    @Slot()
    def run(self) -> None:
        # DropboxBackupService.run() never raises past its own boundary.
        result = self._service.run()
        self.finished.emit(result)
