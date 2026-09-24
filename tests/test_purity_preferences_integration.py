from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

import app as app_module
import ui.main_window as main_window_module
from services.pulse_models import PendingPulse, PulseKind


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FakeSignal:
    def connect(self, _callback) -> None:
        return None


class _FakeWebWatcherService:
    def __init__(self, parent=None):
        self.parent = parent
        self.web_opened = _FakeSignal()
        self.browser_running_changed = _FakeSignal()

    def start(self) -> None:
        return None


class _FakePanicButton:
    def __init__(self, parent=None):
        self.parent = parent
        self.panic_requested = _FakeSignal()

    def set_elevated(self, _value: bool) -> None:
        return None


def test_main_uses_settings_resolved_data_root(monkeypatch, tmp_path: Path) -> None:
    sentinel_manager = object()
    resolved_root = tmp_path / "resolved_root"

    monkeypatch.setattr(app_module, "build_purity_settings_manager", lambda: sentinel_manager)
    monkeypatch.setattr(
        app_module,
        "resolve_purity_data_root",
        lambda manager: resolved_root if manager is sentinel_manager else None,
    )
    monkeypatch.setattr(app_module, "_try_acquire_singleton_mutex", lambda: False)

    captured: dict[str, object] = {}

    def _fake_submit_show_app_request(path: Path, *, source: str) -> None:
        captured["path"] = path
        captured["source"] = source

    monkeypatch.setattr(app_module, "submit_show_app_request", _fake_submit_show_app_request)

    assert app_module.main() == 0
    assert captured == {"path": resolved_root, "source": "app_launch"}


def test_main_uses_ui_main_window_class(monkeypatch, tmp_path: Path) -> None:
    settings_manager = app_module.build_purity_settings_manager(path=tmp_path / "settings.yaml")
    created: dict[str, object] = {}

    class _FakeApp:
        def __init__(self, _argv):
            self.aboutToQuit = _FakeSignal()

        def setStyleSheet(self, _style: str) -> None:
            return None

        def setQuitOnLastWindowClosed(self, _value: bool) -> None:
            return None

        def installEventFilter(self, _event_filter) -> None:
            return None

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(app_module, "build_purity_settings_manager", lambda: settings_manager)
    monkeypatch.setattr(app_module, "resolve_purity_data_root", lambda manager: tmp_path)
    monkeypatch.setattr(app_module, "_try_acquire_singleton_mutex", lambda: True)
    monkeypatch.setattr(app_module, "_find_running_instance", lambda data_root: None)
    monkeypatch.setattr(app_module, "_is_supervisor_running", lambda data_root: True)
    monkeypatch.setattr(app_module, "QApplication", _FakeApp)
    monkeypatch.setattr(app_module, "NotesContextMenuFilter", lambda app: SimpleNamespace())

    class _FakeHeartbeat:
        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    class _FakeTail:
        def flush(self, reason: str) -> None:
            return None

    class _FakeJournal:
        def close_sinks(self) -> None:
            return None

    fake_runtime = SimpleNamespace(
        session=SimpleNamespace(pid=123, run_id="run-1"),
        journal=_FakeJournal(),
        tail=_FakeTail(),
        heartbeat=_FakeHeartbeat(),
        data_root=tmp_path,
    )

    monkeypatch.setattr("services.runtime.create_purity_runtime", lambda data_root: fake_runtime)

    class _FakeBrowserSessionManager:
        def __init__(self, data_root):
            self.data_root = data_root

        def clear_session(self) -> None:
            return None

    class _FakeExtensionHeartbeatMonitor:
        def __init__(self, data_root, stale_after_seconds: float):
            self.data_root = data_root

        def clear(self) -> None:
            return None

    class _FakeApiServer:
        def __init__(self, browser_session_manager, extension_heartbeat_monitor):
            self.browser_session_manager = browser_session_manager
            self.extension_heartbeat_monitor = extension_heartbeat_monitor

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    monkeypatch.setattr(app_module, "BrowserSessionManager", _FakeBrowserSessionManager)
    monkeypatch.setattr(app_module, "ExtensionHeartbeatMonitor", _FakeExtensionHeartbeatMonitor)
    monkeypatch.setattr(app_module, "BrowserSessionApiServer", _FakeApiServer)
    monkeypatch.setattr("services.journal_events.emit_app_started", lambda *args, **kwargs: None)
    monkeypatch.setattr("services.journal_events.emit_app_stopped", lambda *args, **kwargs: None)
    monkeypatch.setattr("services.telegram_notify.build_telegram_adapter_from_settings", lambda settings_manager: SimpleNamespace(send=lambda event: None))
    monkeypatch.setattr("services.web_requests.start_purity_app", lambda data_root: None)
    monkeypatch.setattr("ui.system.supervisor_tray.PurityTrayApp", lambda *args, **kwargs: SimpleNamespace(start=lambda: None))

    class _FakeMainWindow:
        def __init__(self, **kwargs):
            created["kwargs"] = kwargs

        def show(self) -> None:
            return None

        def attach_tray_app(self, tray_app) -> None:
            created["tray_app"] = tray_app

    monkeypatch.setattr(main_window_module, "MainWindow", _FakeMainWindow)

    assert app_module.main() == 0
    assert created["kwargs"]["runtime"] is fake_runtime
    assert created["kwargs"]["settings_manager"] is settings_manager


def test_main_window_builds_preferences_menu(monkeypatch, tmp_path: Path) -> None:
    _app()
    monkeypatch.setattr(main_window_module, "WebWatcherService", _FakeWebWatcherService)
    monkeypatch.setattr(main_window_module, "PanicButton", _FakePanicButton)
    monkeypatch.setattr(main_window_module.MainWindow, "_center_on_screen", lambda self: None)
    monkeypatch.setattr(main_window_module.MainWindow, "_kill_browsers_on_startup", lambda self: None)

    settings_manager = app_module.build_purity_settings_manager(path=tmp_path / "settings.yaml")
    window = main_window_module.MainWindow(runtime=None, settings_manager=settings_manager)

    actions_by_menu = {
        action.text(): [child.text() for child in action.menu().actions()] if action.menu() else []
        for action in window.menuBar().actions()
    }

    assert "File" in actions_by_menu
    assert "Preferences" in actions_by_menu["File"]
    assert "Tools" in actions_by_menu
    assert "View Journals" in actions_by_menu["Tools"]
    assert "Launch Pulse" in actions_by_menu["Tools"]

    window.close()


def test_main_window_opens_due_pulse_expands_dashboard_and_submits(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _app()
    monkeypatch.setattr(main_window_module, "WebWatcherService", _FakeWebWatcherService)
    monkeypatch.setattr(main_window_module, "PanicButton", _FakePanicButton)
    monkeypatch.setattr(main_window_module.MainWindow, "_center_on_screen", lambda self: None)
    monkeypatch.setattr(main_window_module.MainWindow, "_kill_browsers_on_startup", lambda self: None)

    settings_manager = app_module.build_purity_settings_manager(path=tmp_path / "settings.yaml")
    window = main_window_module.MainWindow(runtime=None, settings_manager=settings_manager)

    calls: dict[str, object] = {}
    monkeypatch.setattr(
        window._left_dock, "start_prayer_session", lambda names: calls.__setitem__("names", names)
    )
    monkeypatch.setattr(window._left_dock, "expand", lambda: calls.__setitem__("expanded", True))

    pending = PendingPulse(
        pulse_id="pulse-1",
        pulse_kind=PulseKind.MORNING,
        day="2026-06-09",
        prompted_local_ts=datetime(
            2026,
            6,
            9,
            9,
            0,
            tzinfo=timezone(timedelta(hours=10)),
        ).isoformat(),
    )

    class _FakePulseManager:
        def poll_due_pulse(self):
            return pending

        def submit_pulse(self, **kwargs):
            calls["submit_pulse"] = kwargs

    window._pulse_manager = _FakePulseManager()

    window._poll_pulse_due()

    assert calls["expanded"] is True
    assert calls["names"] == []
    assert calls["submit_pulse"]["pending"] is pending

    window.close()