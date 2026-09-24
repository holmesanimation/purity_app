from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from services.backup.controller import BackupController
from services.settings_schemas import build_purity_settings_manager
from ui.backup.backup_dialog import BackupDialog


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_backup_dialog_shows_unconfigured_destination(tmp_path: Path) -> None:
    app = _app()
    settings_manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    controller = BackupController(settings_manager)

    dialog = BackupDialog(controller, settings_manager)
    app.processEvents()

    assert dialog._destination_label is not None
    assert "not configured" in dialog._destination_label.text()
    assert dialog._back_up_now_btn is not None
    assert dialog._back_up_now_btn.isEnabled() is False


def test_back_up_now_runs_off_gui_thread_and_updates_status(tmp_path: Path) -> None:
    app = _app()
    settings_manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    data_root = tmp_path / "data_root"
    data_root.mkdir()
    settings_manager.set("app.general", "data_root", str(data_root))
    destination_root = tmp_path / "dest"
    settings_manager.set("app.general", "backup_local_destination", str(destination_root))

    controller = BackupController(settings_manager)
    dialog = BackupDialog(controller, settings_manager)

    loop = QEventLoop()
    controller.run_finished.connect(lambda _result: loop.quit())
    QTimer.singleShot(10_000, loop.quit)  # safety net against a hung worker

    dialog._on_back_up_now_clicked()
    assert dialog._back_up_now_btn.isEnabled() is False
    loop.exec()

    assert dialog._back_up_now_btn.isEnabled() is True
    assert "Last run" in dialog._last_run_label.text()
    assert destination_root.exists()

    # Let the worker's QThread fully quit before the test ends, so its C++
    # teardown doesn't race with a later test's QObject construction.
    if controller._thread is not None:
        controller._thread.wait(2000)
    app.processEvents()
