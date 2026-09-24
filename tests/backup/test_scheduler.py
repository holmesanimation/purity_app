from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from services.backup.scheduler import (
    BackupSchedule,
    ScheduleState,
    is_due,
    last_occurrence_at_or_before,
    load_schedule_state,
    save_schedule_state,
)

_UTC = ZoneInfo("UTC")


def _schedule(**overrides) -> BackupSchedule:
    base = {"enabled": True, "weekday": 6, "time": "02:00", "timezone": "UTC"}  # Sunday 02:00
    base.update(overrides)
    return BackupSchedule(**base)


def test_disabled_schedule_never_due() -> None:
    schedule = _schedule(enabled=False)
    now = datetime(2026, 9, 20, 3, 0, tzinfo=_UTC)  # Sunday, after 02:00
    assert is_due(now, schedule, ScheduleState()) is None


def test_due_when_past_scheduled_time_and_not_yet_evaluated() -> None:
    schedule = _schedule()
    now = datetime(2026, 9, 20, 3, 0, tzinfo=_UTC)  # Sunday 2026-09-20, 03:00 UTC
    occ_id = is_due(now, schedule, ScheduleState())
    assert occ_id is not None


def test_not_due_before_scheduled_time_same_day() -> None:
    schedule = _schedule()
    now = datetime(2026, 9, 20, 1, 0, tzinfo=_UTC)  # Sunday, before 02:00
    occurrence = last_occurrence_at_or_before(now, schedule)
    # scheduled time not yet reached today -> falls back to the previous Sunday
    assert occurrence.date() == datetime(2026, 9, 13).date()


def test_already_evaluated_occurrence_is_not_due_again() -> None:
    schedule = _schedule()
    now = datetime(2026, 9, 20, 3, 0, tzinfo=_UTC)
    occ_id = is_due(now, schedule, ScheduleState())
    assert occ_id is not None

    state = ScheduleState(last_evaluated_occurrence_id=occ_id)
    assert is_due(now, schedule, state) is None
    # still not due later the same day/occurrence window
    later_same_occurrence = datetime(2026, 9, 20, 23, 0, tzinfo=_UTC)
    assert is_due(later_same_occurrence, schedule, state) is None


def test_restart_safety_reload_from_disk_prevents_duplicate_run(tmp_path) -> None:
    schedule = _schedule()
    now = datetime(2026, 9, 20, 3, 0, tzinfo=_UTC)
    occ_id = is_due(now, schedule, ScheduleState())
    assert occ_id is not None

    state = ScheduleState(last_evaluated_occurrence_id=occ_id, last_run_result_ref="run-1")
    save_schedule_state(tmp_path, state)

    reloaded = load_schedule_state(tmp_path)
    assert reloaded.last_evaluated_occurrence_id == occ_id
    assert reloaded.last_run_result_ref == "run-1"
    assert is_due(now, schedule, reloaded) is None


def test_new_occurrence_next_week_becomes_due_again() -> None:
    schedule = _schedule()
    first_now = datetime(2026, 9, 20, 3, 0, tzinfo=_UTC)
    first_occ_id = is_due(first_now, schedule, ScheduleState())
    state = ScheduleState(last_evaluated_occurrence_id=first_occ_id)

    next_week_now = datetime(2026, 9, 27, 3, 0, tzinfo=_UTC)
    next_occ_id = is_due(next_week_now, schedule, state)
    assert next_occ_id is not None
    assert next_occ_id != first_occ_id


def test_timezone_affects_absolute_occurrence_time() -> None:
    utc_schedule = _schedule(timezone="UTC")
    ny_schedule = _schedule(timezone="America/New_York")
    now = datetime(2026, 9, 20, 12, 0, tzinfo=_UTC)

    utc_occurrence = last_occurrence_at_or_before(now, utc_schedule)
    ny_occurrence = last_occurrence_at_or_before(now, ny_schedule)

    # Same wall-clock schedule (02:00 Sunday) in different timezones is a
    # different absolute instant.
    assert utc_occurrence.astimezone(_UTC) != ny_occurrence.astimezone(_UTC)


def test_dst_spring_forward_produces_valid_occurrence() -> None:
    # 2026-03-08 is the US DST spring-forward date (America/New_York).
    schedule = _schedule(weekday=6, time="02:00", timezone="America/New_York")
    now = datetime(2026, 3, 9, 12, 0, tzinfo=_UTC)
    occurrence = last_occurrence_at_or_before(now, schedule)
    assert occurrence.tzinfo is not None
    # Must not raise and must resolve to a real, well-defined instant.
    occurrence.astimezone(_UTC)


def test_schedule_state_defaults_when_no_file(tmp_path) -> None:
    state = load_schedule_state(tmp_path)
    assert state.last_evaluated_occurrence_id is None
    assert state.last_run_result_ref is None
