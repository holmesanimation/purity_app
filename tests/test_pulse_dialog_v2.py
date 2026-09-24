from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import QApplication

from services.pulse_models import PendingPulse, PulseKind
from ui.pulse_dialog_v2 import PulseDialogV2


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _pending() -> PendingPulse:
    return PendingPulse(
        pulse_id="pulse-1",
        pulse_kind=PulseKind.MORNING,
        day="2026-06-09",
        prompted_local_ts=datetime(
            2026, 6, 9, 9, 0, tzinfo=timezone(timedelta(hours=10))
        ).isoformat(),
    )


def test_shows_random_recipient_name() -> None:
    _app()
    dialog = PulseDialogV2(
        pending=_pending(),
        submit_pulse=lambda **kwargs: None,
        prayer_recipient_names=["Mom"],
    )
    assert dialog._journal_panel._prayer_recipient_name == "Mom"
    dialog.close()


def test_done_always_enabled_and_submits_empty_pulse() -> None:
    _app()
    submitted: dict[str, object] = {}
    dialog = PulseDialogV2(
        pending=_pending(),
        submit_pulse=lambda **kwargs: submitted.update(kwargs),
        prayer_recipient_names=[],
    )
    dialog._on_done()
    assert submitted["answers"] == {}
    assert dialog._completed is True
    dialog.close()


def test_tag_prayer_recipient_commits_with_prayer_owner_and_unchecks(tmp_path, monkeypatch) -> None:
    _app()
    dialog = PulseDialogV2(
        pending=_pending(),
        submit_pulse=lambda **kwargs: None,
        prayer_recipient_names=["Mom"],
    )
    panel = dialog._journal_panel

    committed: list = []
    monkeypatch.setattr(panel._prayer_notes_writer, "commit", lambda note: committed.append(note))

    panel._free_input.setPlainText("Praying for Mom")
    panel._tag_prayer_btn.setChecked(True)
    panel._save_free()

    assert len(committed) == 1
    assert committed[0].owner == "Prayer"
    assert "Mom" in committed[0].context["tags"]
    assert panel._tag_prayer_btn.isChecked() is False
    dialog.close()
