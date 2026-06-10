from __future__ import annotations

from pathlib import Path

from services.pulse_models import PulseDayState, PulseKind, PulseRecord, PulseSliders
from services.pulse_store import PulseStore


def test_load_day_returns_default_empty_state(tmp_path: Path) -> None:
    store = PulseStore(tmp_path)

    state = store.load_day("2026-06-09")

    assert state == PulseDayState(day="2026-06-09")


def test_append_record_persists_pulse_payload_and_reach_out_fields(tmp_path: Path) -> None:
    store = PulseStore(tmp_path)
    record = PulseRecord(
        pulse_id="pulse-123",
        pulse_kind=PulseKind.EVENING,
        submitted_local_ts="2026-06-09T21:15:00+10:00",
        prompted_local_ts="2026-06-09T21:12:00+10:00",
        sliders=PulseSliders(energy=-3, faith=-1, encouragement=-2, temptation=-4),
        answers={
            "what_are_you_doing_right_now": "Scrolling around aimlessly.",
            "how_long_do_you_plan_to_keep_doing_it": "30m",
        },
        note_text="Need to reset my attention.",
        reach_out_text="Hey guys, I feel discouraged and tired tonight.",
        reach_out_sent=True,
        evening_duration_choice="30m",
    )

    updated = store.append_record("2026-06-09", record)
    reloaded = store.load_day("2026-06-09")

    assert updated.records[0].pulse_id == "pulse-123"
    assert len(reloaded.records) == 1
    saved = reloaded.records[0]
    assert saved.pulse_kind is PulseKind.EVENING
    assert saved.sliders.energy == -3
    assert saved.sliders.faith == -1
    assert saved.sliders.encouragement == -2
    assert saved.sliders.temptation == -4
    assert saved.answers["how_long_do_you_plan_to_keep_doing_it"] == "30m"
    assert saved.note_text == "Need to reset my attention."
    assert saved.reach_out_text == "Hey guys, I feel discouraged and tired tonight."
    assert saved.reach_out_sent is True
    assert saved.evening_duration_choice == "30m"


def test_update_prompt_state_persists_scheduler_metadata(tmp_path: Path) -> None:
    store = PulseStore(tmp_path)

    updated = store.update_prompt_state(
        "2026-06-09",
        pulse_kind="evening",
        prompted_local_ts="2026-06-09T21:00:00+10:00",
        next_evening_due_local_ts="2026-06-09T21:30:00+10:00",
        last_activity_local_ts="2026-06-09T21:05:00+10:00",
    )

    assert updated.last_prompted_kind == "evening"
    assert updated.last_prompted_local_ts == "2026-06-09T21:00:00+10:00"
    assert updated.next_evening_due_local_ts == "2026-06-09T21:30:00+10:00"
    assert updated.last_activity_local_ts == "2026-06-09T21:05:00+10:00"

    reloaded = store.load_day("2026-06-09")
    assert reloaded.last_prompted_kind == "evening"
    assert reloaded.next_evening_due_local_ts == "2026-06-09T21:30:00+10:00"