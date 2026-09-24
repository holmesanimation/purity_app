"""BackupController — Qt glue between UI (tray/dialog) and BackupService.

Owned by app.py; both the tray action and BackupDialog call
``back_up_now()``. Runs ``BackupService.run()`` on a background QThread so
the GUI thread never touches files/hashes, and enforces the single-flight
lock so overlapping manual (and later, scheduled) triggers cannot double-run.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from shane_common.preferences import SettingsManager

from services.settings_schemas import get_backup_local_destination

from .lock import SingleFlightLock
from .models import BackupRunResult
from .service import BackupService


class BackupController(QObject):
    run_started = Signal()
    run_finished = Signal(object)  # BackupRunResult
    run_rejected = Signal(str)  # human-readable reason

    def __init__(self, settings_manager: SettingsManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager
        self._service = BackupService(settings_manager=settings_manager)
        self._lock = SingleFlightLock()
        self._thread: QThread | None = None
        self._worker: "_BackupWorker | None" = None

    @property
    def is_running(self) -> bool:
        return self._lock.locked

    def back_up_now(self, family_names: set[str] | None = None) -> bool:
        """Start a backup run in the background. Returns False if rejected."""
        destination = get_backup_local_destination(self._settings_manager)
        if destination is None:
            self.run_rejected.emit("No local backup destination configured.")
            return False
        if not self._lock.try_acquire():
            self.run_rejected.emit("A backup run is already in progress.")
            return False

        self._thread = QThread(self)
        self._worker = _BackupWorker(self._service, destination, family_names)
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


class _BackupWorker(QObject):
    finished = Signal(object)  # BackupRunResult

    def __init__(
        self, service: BackupService, destination: Path, family_names: set[str] | None = None
    ) -> None:
        super().__init__()
        self._service = service
        self._destination = destination
        self._family_names = family_names

    @Slot()
    def run(self) -> None:
        # BackupService.run() never raises past its own boundary.
        result = self._service.run(self._destination, self._family_names)
        self.finished.emit(result)
