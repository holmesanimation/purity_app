import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from purity_app.ui.system.log_viewer_window import PurityLogViewerWindow, _load_disk_rows
from purity_app.ui.system.log_normalizer_sink import PurityLogNormalizerSink
from purity_app.services.log_kind_map import TYPE_SYSTEM, TYPE_WEB, TYPE_INTERVENTION
from shane_common.ui.log_viewer.log_row import LogRow


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_type_combobox_filters_rows() -> None:
    app = _app()
    sink = PurityLogNormalizerSink()
    window = PurityLogViewerWindow(sink=sink)

    window.append_row(LogRow(1.0, "system.start", "INFO", "system.start", None, "started"))
    window.append_row(LogRow(2.0, "chrome.allowed", "INFO", "chrome.allowed", None, "allowed"))
    app.processEvents()

    assert window._proxy.rowCount() == 2

    index = window._type_combo.findData(TYPE_SYSTEM)
    window._type_combo.setCurrentIndex(index)
    app.processEvents()
    assert window._proxy.rowCount() == 1


def test_journal_viewer_loads_disk_journal_rows(tmp_path: Path) -> None:
    app = _app()
    journal_dir = tmp_path / "_system" / "purity" / "journals" / "2026-05-19"
    journal_dir.mkdir(parents=True)
    event = {
        "local_TS": "2026-05-19T10:45:00-06:00",
        "ts": "2026-05-19T16:45:00+00:00",
        "run_id": "launcher-run",
        "kind": "chrome.allowed",
        "source": {"app": "purity_app", "component": "chrome_watcher"},
        "payload": {
            "allowed": True,
            "choice": "Work",
            "reason": "Need to check a reference.",
        },
    }
    (journal_dir / "chrome.jsonl").write_text(
        json.dumps(event, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    rows = _load_disk_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0].kind == "chrome.allowed"
    assert "Need to check a reference." in rows[0].message

    window = PurityLogViewerWindow(sink=PurityLogNormalizerSink(), data_root=tmp_path)
    app.processEvents()
    assert window._proxy.rowCount() == 1

    index = window._type_combo.findData(TYPE_WEB)
    window._type_combo.setCurrentIndex(index)
    app.processEvents()
    assert window._proxy.rowCount() == 1


def test_panic_reflection_saved_loads_as_intervention_row(tmp_path: Path) -> None:
    """panic.reflection_saved events in panic.jsonl load and display as Intervention rows."""
    app = _app()
    journal_dir = tmp_path / "_system" / "purity" / "journals" / "2026-05-27"
    journal_dir.mkdir(parents=True)
    event = {
        "local_TS": "2026-05-27T09:15:00-06:00",
        "ts": "2026-05-27T15:15:00+00:00",
        "run_id": "test-run",
        "kind": "panic.reflection_saved",
        "source": {"app": "purity_app", "component": "panic"},
        "payload": {
            "panic_session_id": "abc-123",
            "reason_id": "lonely",
        },
    }
    (journal_dir / "panic.jsonl").write_text(
        json.dumps(event, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    rows = _load_disk_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0].kind == "panic.reflection_saved"

    window = PurityLogViewerWindow(sink=PurityLogNormalizerSink(), data_root=tmp_path)
    app.processEvents()
    assert window._proxy.rowCount() == 1

    # Filter to Intervention — the panic row must remain visible.
    index = window._type_combo.findData(TYPE_INTERVENTION)
    window._type_combo.setCurrentIndex(index)
    app.processEvents()
    assert window._proxy.rowCount() == 1

    # Filtering to a different type hides the panic row.
    index = window._type_combo.findData(TYPE_WEB)
    window._type_combo.setCurrentIndex(index)
    app.processEvents()
    assert window._proxy.rowCount() == 0