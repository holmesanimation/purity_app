import time
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, QMetaObject, QThread, QTimer, Qt, Signal, Slot
from shane_common.processes.windows import has_visible_window

_WATCHED_BROWSERS = ('chrome.exe', 'msedge.exe')
_POLL_MS = 2000
# Marker written by web_launcher.py when it approves a browser open.
# Prevents a double-popup when both the shortcut and the watcher fire.
_APPROVED_MARKER = Path(tempfile.gettempdir()) / 'purity_web_approved'
_APPROVED_WINDOW_SECS = 10


def _launcher_just_approved() -> bool:
    try:
        ts = float(_APPROVED_MARKER.read_text(encoding='utf-8'))
        return (time.time() - ts) < _APPROVED_WINDOW_SECS
    except Exception:
        return False


class WebWatcherService(QObject):
    web_opened = Signal(str)  # emits the exe name that triggered, e.g. 'chrome.exe'
    browser_running_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = _WebWatcherWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._thread.finished.connect(self._worker.deleteLater)
        self._worker.web_opened.connect(self.web_opened)
        self._worker.browser_running_changed.connect(self.browser_running_changed)

    def start(self):
        if self._thread.isRunning():
            return
        self._thread.start()

    def stop(self) -> None:
        if not self._thread.isRunning():
            return
        QMetaObject.invokeMethod(
            self._worker,
            "stop",
            Qt.ConnectionType.BlockingQueuedConnection,
        )
        self._thread.quit()
        self._thread.wait()


class _WebWatcherWorker(QObject):
    web_opened = Signal(str)
    browser_running_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._was_running: dict[str, bool] = {}
        self._any_running: bool = False
        self._timer: QTimer | None = None

    @Slot()
    def start(self) -> None:
        self._was_running = {exe: has_visible_window(exe) for exe in _WATCHED_BROWSERS}
        any_running = any(self._was_running.values())
        self._set_any_running(any_running)

        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setInterval(_POLL_MS)
            self._timer.timeout.connect(self._poll)
        self._timer.start()

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    @Slot()
    def _poll(self):
        fired = False
        any_running = False
        launcher_approved = _launcher_just_approved()
        for exe in _WATCHED_BROWSERS:
            is_running = has_visible_window(exe)
            any_running = any_running or is_running
            just_opened = is_running and not self._was_running.get(exe, False)
            self._was_running[exe] = is_running
            if just_opened and not fired and not launcher_approved:
                fired = True
                self.web_opened.emit(exe)
        self._set_any_running(any_running)

    def _set_any_running(self, any_running: bool) -> None:
        any_running = bool(any_running)
        if any_running == self._any_running:
            return
        self._any_running = any_running
        self.browser_running_changed.emit(any_running)
