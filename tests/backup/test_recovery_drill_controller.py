from __future__ import annotations

import gc
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QTimer
from PySide6.QtWidgets import QApplication

from services.backup.recovery_drill_controller import RecoveryDrillController
from services.settings_schemas import build_purity_settings_manager


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _settle(app: QApplication) -> None:
    """Drains the event loop and lets Qt fully tear down finished QThreads
    before the next test constructs new ones (avoids cross-test GC/threading
    flakiness observed with back-to-back QThread-based controller tests)."""
    for _ in range(5):
        app.processEvents()
    gc.collect()
    for _ in range(5):
        app.processEvents()


class _StubController(QObject):
    """Minimal stand-in for BackupController/DropboxController exposing only
    the ``is_running`` property RecoveryDrillController reads — avoids
    spinning up real QThread-backed controllers in these unit tests."""

    def __init__(self, is_running: bool = False) -> None:
        super().__init__()
        self.is_running = is_running


def _make_recovery_controller(
    tmp_path: Path, *, local_running: bool = False, dropbox_running: bool = False
):
    settings_manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    backup_controller = _StubController(local_running)
    dropbox_controller = _StubController(dropbox_running)
    recovery_controller = RecoveryDrillController(settings_manager, backup_controller, dropbox_controller)
    return settings_manager, recovery_controller


def test_run_drill_executes_and_reports_finished(tmp_path: Path, monkeypatch) -> None:
    app = _app()
    _settle(app)
    settings_manager, recovery_controller = _make_recovery_controller(tmp_path)

    from services.backup import recovery_drill

    monkeypatch.setattr(recovery_drill, "run_local_drill", lambda _sm: "LOCAL_RESULT")
    monkeypatch.setattr(recovery_drill, "run_dropbox_drill", lambda _sm: "DROPBOX_RESULT")

    loop = QEventLoop()
    results = {}

    def _on_finished(payload: dict) -> None:
        results.update(payload)
        loop.quit()

    recovery_controller.drill_finished.connect(_on_finished)
    assert recovery_controller.run_drill() is True

    QTimer.singleShot(10_000, loop.quit)
    loop.exec()

    assert results.get("local") == "LOCAL_RESULT"
    assert results.get("dropbox") == "DROPBOX_RESULT"
    assert recovery_controller.is_running is False
    _settle(app)


def test_duplicate_run_rejected_while_running(tmp_path: Path, monkeypatch) -> None:
    app = _app()
    _settle(app)
    settings_manager, recovery_controller = _make_recovery_controller(tmp_path)

    from services.backup import recovery_drill

    monkeypatch.setattr(recovery_drill, "run_local_drill", lambda _sm: None)
    monkeypatch.setattr(recovery_drill, "run_dropbox_drill", lambda _sm: None)

    assert recovery_controller.run_drill() is True
    rejected = []
    recovery_controller.drill_rejected.connect(lambda reason: rejected.append(reason))

    assert recovery_controller.run_drill() is False
    assert rejected

    loop = QEventLoop()
    recovery_controller.drill_finished.connect(lambda _r: loop.quit())
    QTimer.singleShot(10_000, loop.quit)
    loop.exec()
    _settle(app)


def test_local_drill_skipped_while_local_backup_running(tmp_path: Path, monkeypatch) -> None:
    app = _app()
    _settle(app)
    settings_manager, recovery_controller = _make_recovery_controller(tmp_path, local_running=True)

    from services.backup import recovery_drill

    calls = {"local": False, "dropbox": False}

    def _local(_sm):
        calls["local"] = True
        return "SHOULD_NOT_RUN"

    def _dropbox(_sm):
        calls["dropbox"] = True
        return "DROPBOX_RESULT"

    monkeypatch.setattr(recovery_drill, "run_local_drill", _local)
    monkeypatch.setattr(recovery_drill, "run_dropbox_drill", _dropbox)

    loop = QEventLoop()
    results = {}

    def _on_finished(payload: dict) -> None:
        results.update(payload)
        loop.quit()

    recovery_controller.drill_finished.connect(_on_finished)
    assert recovery_controller.run_drill() is True
    QTimer.singleShot(10_000, loop.quit)
    loop.exec()

    assert calls["local"] is False
    assert calls["dropbox"] is True
    assert results.get("local") is None
    assert results.get("dropbox") == "DROPBOX_RESULT"
    _settle(app)
    _settle(app)
