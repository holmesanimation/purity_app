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


def test_reach_out_button_always_present_in_state_group() -> None:
    _app()
    dialog = PulseDialog(
        pending=_pending(PulseKind.MORNING),
        submit_pulse=lambda **kwargs: None,
        submit_note=lambda text: None,
        send_reach_out=lambda sliders, text: None,
    )

    # The reach-out button lives inside the My State group and is always visible
    from PySide6.QtWidgets import QPushButton

    state_group = dialog._state_groups[0].parent()
    reach_out_btns = [
        w for w in state_group.findChildren(QPushButton)
        if "Reach Out" in w.text()
    ]
    assert len(reach_out_btns) == 1
    assert reach_out_btns[0].isHidden() is False

    dialog.close()


def test_submit_disabled_until_all_state_rows_selected() -> None:
    _app()
    submitted: dict[str, object] = {}
    dialog = PulseDialog(
        pending=_pending(PulseKind.MORNING),
        submit_pulse=lambda **kwargs: submitted.update(kwargs),
        submit_note=lambda text: None,
        send_reach_out=lambda sliders, text: None,
    )

    assert dialog._submit_btn.isEnabled() is False

    # Check one row at a time
    dialog._state_groups[0].button(0).setChecked(True)
    assert dialog._submit_btn.isEnabled() is False

    dialog._state_groups[1].button(0).setChecked(True)
    assert dialog._submit_btn.isEnabled() is False

    dialog._state_groups[2].button(0).setChecked(True)
    assert dialog._submit_btn.isEnabled() is True

    dialog.close()


def test_submit_passes_correct_answers() -> None:
    _app()
    submitted: dict[str, object] = {}
    dialog = PulseDialog(
        pending=_pending(PulseKind.MORNING),
        submit_pulse=lambda **kwargs: submitted.update(kwargs),
        submit_note=lambda text: None,
        send_reach_out=lambda sliders, text: None,
    )

    # Select all state rows (positive)
    for group in dialog._state_groups:
        group.button(0).setChecked(True)

    dialog._vitamins_btn.setChecked(True)
    dialog._physical_activity_edit.setPlainText("Running")

    dialog._on_submit_pulse()

    assert submitted["answers"]["took_vitamins"] is True
    assert submitted["answers"]["physical_activity"] == "Running"
    assert submitted["evening_duration_choice"] is None
    dialog.close()