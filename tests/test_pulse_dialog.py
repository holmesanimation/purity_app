from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import QApplication

from services.pulse_models import PendingPulse, PulseKind
from ui.pulse_dialog import PulseDialog


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _pending(pulse_kind: PulseKind) -> PendingPulse:
    return PendingPulse(
        pulse_id="pulse-1",
        pulse_kind=pulse_kind,
        day="2026-06-09",
        prompted_local_ts=datetime(
            2026, 6, 9, 9, 0, tzinfo=timezone(timedelta(hours=10))
        ).isoformat(),
    )


def test_reach_out_group_hidden_until_any_slider_is_negative() -> None:
    _app()
    dialog = PulseDialog(
        pending=_pending(PulseKind.MORNING),
        submit_pulse=lambda **kwargs: None,
        submit_note=lambda text: None,
        send_reach_out=lambda sliders, text: None,
    )

    assert dialog._reach_out_group.isHidden() is True

    dialog._slider_widgets["energy"].setValue(-1)
    assert dialog._reach_out_group.isHidden() is False

    dialog._slider_widgets["energy"].setValue(0)
    assert dialog._reach_out_group.isHidden() is True

    dialog.close()


def test_manual_pulse_shows_all_questions_and_allows_empty_submit() -> None:
    _app()
    submitted: dict[str, object] = {}
    dialog = PulseDialog(
        pending=_pending(PulseKind.MANUAL),
        submit_pulse=lambda **kwargs: submitted.update(kwargs),
        submit_note=lambda text: None,
        send_reach_out=lambda sliders, text: None,
    )

    assert hasattr(dialog, "_scripture_edit")
    assert hasattr(dialog, "_physical_activity_edit")
    assert hasattr(dialog, "_evening_activity_edit")

    dialog._on_submit_pulse()

    assert submitted["answers"]["scripture_learning"] == ""
    assert submitted["answers"]["physical_activity"] == ""
    assert submitted["answers"]["what_are_you_doing_right_now"] == ""
    assert submitted["evening_duration_choice"] == "5m"
    dialog.close()