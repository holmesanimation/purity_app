from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from purity_app.services.browser_session import ExtensionHeartbeatMonitor
from purity_app.services.supervisor_client import PuritySupervisorClient
from purity_app.ui.system.supervisor_tray import PurityStatusWindow


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_status_window_shows_extension_heartbeat_status(tmp_path: Path) -> None:
    _app()
    client = PuritySupervisorClient(tmp_path)
    monitor = ExtensionHeartbeatMonitor(tmp_path)
    monitor.record_heartbeat(extension_version="0.1.0", instance_id="abc123")

    window = PurityStatusWindow(client)
    window.refresh()

    assert window._extension_status_label is not None
    assert "extension heartbeat: HEALTHY" in window._extension_status_label.text()
    assert "v0.1.0" in window._extension_status_label.text()
    assert "color:" in window._extension_status_label.styleSheet()