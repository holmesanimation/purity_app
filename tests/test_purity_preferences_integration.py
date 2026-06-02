from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

import app as app_module


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

    def start(self) -> None:
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


def test_main_window_builds_preferences_menu(monkeypatch, tmp_path: Path) -> None:
    _app()
    monkeypatch.setattr(app_module, "WebWatcherService", _FakeWebWatcherService)
    monkeypatch.setattr(app_module.MainWindow, "_center_on_screen", lambda self: None)
    monkeypatch.setattr(app_module.MainWindow, "_kill_browsers_on_startup", lambda self: None)

    settings_manager = app_module.build_purity_settings_manager(path=tmp_path / "settings.yaml")
    window = app_module.MainWindow(runtime=None, settings_manager=settings_manager)

    actions_by_menu = {
        action.text(): [child.text() for child in action.menu().actions()] if action.menu() else []
        for action in window.menuBar().actions()
    }

    assert "File" in actions_by_menu
    assert "Preferences" in actions_by_menu["File"]
    assert "Tools" in actions_by_menu
    assert "View Journals" in actions_by_menu["Tools"]

    window.close()