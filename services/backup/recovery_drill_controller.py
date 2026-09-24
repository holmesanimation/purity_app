"""RecoveryDrillController — Qt glue running the P6-based monthly recovery drill.

Mirrors ``BackupController``/``DropboxController``: owns its own
single-flight lock (so a duplicate click cannot start a second drill), runs
the drill on a background ``QThread`` (all file/hash/network work happens in
``recovery_drill.py``, never on the GUI thread), and refuses to drill a
destination while that same destination's backup/upload controller is
currently running (LOCAL backup active -> skip LOCAL drill this run; Dropbox
upload active -> skip DROPBOX drill this run) to avoid verifying a
destination mid-mutation. Unrelated destinations are not serialized against
each other.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from shane_common.preferences import SettingsManager

from . import recovery_drill
from .controller import BackupController
from .dropbox_controller import DropboxController
from .lock import SingleFlightLock


class RecoveryDrillController(QObject):
    drill_started = Signal()
    drill_finished = Signal(dict)  # {"local": RestoreResult|None, "dropbox": RestoreResult|str|None}
    drill_rejected = Signal(str)

    def __init__(
        self,
        settings_manager: SettingsManager,
        backup_controller: BackupController,
        dropbox_controller: DropboxController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager
        self._backup_controller = backup_controller
        self._dropbox_controller = dropbox_controller
        self._lock = SingleFlightLock()
        self._thread: QThread | None = None
        self._worker: "_RecoveryDrillWorker | None" = None

    @property
    def is_running(self) -> bool:
        return self._lock.locked

    def run_drill(self) -> bool:
        """Starts the drill in the background. Returns False if rejected."""
        if not self._lock.try_acquire():
            self.drill_rejected.emit("A recovery drill is already in progress.")
            return False

        skip_local = self._backup_controller.is_running
        skip_dropbox = self._dropbox_controller.is_running

        self._thread = QThread(self)
        self._worker = _RecoveryDrillWorker(self._settings_manager, skip_local, skip_dropbox)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self.drill_started.emit()
        self._thread.start()
        return True

    @Slot(dict)
    def _on_finished(self, results: dict) -> None:
        self._lock.release()
        self.drill_finished.emit(results)


class _RecoveryDrillWorker(QObject):
    finished = Signal(dict)

    def __init__(self, settings_manager: SettingsManager, skip_local: bool, skip_dropbox: bool) -> None:
        super().__init__()
        self._settings_manager = settings_manager
        self._skip_local = skip_local
        self._skip_dropbox = skip_dropbox

    @Slot()
    def run(self) -> None:
        local_result = None
        if not self._skip_local:
            local_result = recovery_drill.run_local_drill(self._settings_manager)

        dropbox_result = None
        if not self._skip_dropbox:
            dropbox_result = recovery_drill.run_dropbox_drill(self._settings_manager)

        self.finished.emit({"local": local_result, "dropbox": dropbox_result})
