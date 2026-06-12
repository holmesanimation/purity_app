from __future__ import annotations

from PySide6.QtCore import QObject, QMetaObject, QThread, QTimer, Qt, Signal, Slot

from services.browser_session import BrowserSessionManager, ExtensionHeartbeatMonitor


_SESSION_POLL_MS = 500
_HEARTBEAT_POLL_MS = 2_000


class BrowserSessionWatcher(QObject):
    session_payload_changed = Signal(dict)
    heartbeat_healthy_changed = Signal(bool)

    def __init__(
        self,
        *,
        session_manager: BrowserSessionManager | None,
        heartbeat_monitor: ExtensionHeartbeatMonitor | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = _BrowserSessionWatcherWorker(
            session_manager=session_manager,
            heartbeat_monitor=heartbeat_monitor,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._thread.finished.connect(self._worker.deleteLater)
        self._worker.session_payload_changed.connect(self.session_payload_changed)
        self._worker.heartbeat_healthy_changed.connect(self.heartbeat_healthy_changed)

    def start(self) -> None:
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


class _BrowserSessionWatcherWorker(QObject):
    session_payload_changed = Signal(dict)
    heartbeat_healthy_changed = Signal(bool)

    def __init__(
        self,
        *,
        session_manager: BrowserSessionManager | None,
        heartbeat_monitor: ExtensionHeartbeatMonitor | None,
    ) -> None:
        super().__init__()
        self._session_manager = session_manager
        self._heartbeat_monitor = heartbeat_monitor
        self._session_timer: QTimer | None = None
        self._heartbeat_timer: QTimer | None = None
        self._last_session_payload: dict | None = None
        self._last_heartbeat_healthy: bool | None = None

    @Slot()
    def start(self) -> None:
        if self._session_manager is not None:
            if self._session_timer is None:
                self._session_timer = QTimer(self)
                self._session_timer.setInterval(_SESSION_POLL_MS)
                self._session_timer.timeout.connect(self._poll_session_payload)
            self._poll_session_payload()
            self._session_timer.start()

        if self._heartbeat_monitor is not None:
            if self._heartbeat_timer is None:
                self._heartbeat_timer = QTimer(self)
                self._heartbeat_timer.setInterval(_HEARTBEAT_POLL_MS)
                self._heartbeat_timer.timeout.connect(self._poll_heartbeat_healthy)
            self._poll_heartbeat_healthy()
            self._heartbeat_timer.start()

    @Slot()
    def stop(self) -> None:
        if self._session_timer is not None:
            self._session_timer.stop()
        if self._heartbeat_timer is not None:
            self._heartbeat_timer.stop()

    @Slot()
    def _poll_session_payload(self) -> None:
        if self._session_manager is None:
            return
        payload = self._session_manager.get_session_payload()
        if payload == self._last_session_payload:
            return
        self._last_session_payload = dict(payload)
        self.session_payload_changed.emit(dict(payload))

    @Slot()
    def _poll_heartbeat_healthy(self) -> None:
        if self._heartbeat_monitor is None:
            return
        is_healthy = bool(self._heartbeat_monitor.is_healthy())
        if is_healthy == self._last_heartbeat_healthy:
            return
        self._last_heartbeat_healthy = is_healthy
        self.heartbeat_healthy_changed.emit(is_healthy)