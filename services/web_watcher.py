import time
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._was_running: dict[str, bool] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._poll)

    def start(self):
        self._was_running = {exe: has_visible_window(exe) for exe in _WATCHED_BROWSERS}
        self._timer.start()

    def _poll(self):
        fired = False
        for exe in _WATCHED_BROWSERS:
            is_running = has_visible_window(exe)
            just_opened = is_running and not self._was_running.get(exe, False)
            self._was_running[exe] = is_running
            if just_opened and not fired and not _launcher_just_approved():
                fired = True
                self.web_opened.emit(exe)
