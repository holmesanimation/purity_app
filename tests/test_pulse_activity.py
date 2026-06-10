from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.pulse_activity import UserActivityMonitor


def test_first_poll_initializes_baseline_without_marking_activity() -> None:
    now = datetime(2026, 6, 9, 9, 0, tzinfo=timezone(timedelta(hours=10)))
    monitor = UserActivityMonitor(
        clock_fn=lambda: now,
        cursor_reader=lambda: (100, 100),
        input_tick_reader=lambda: 1000,
    )

    snapshot = monitor.poll()

    assert snapshot.had_new_activity is False
    assert snapshot.last_activity_at is None


def test_cursor_movement_marks_new_activity() -> None:
    current = datetime(2026, 6, 9, 9, 0, tzinfo=timezone(timedelta(hours=10)))
    cursor_positions = iter([(100, 100), (120, 130)])
    monitor = UserActivityMonitor(
        clock_fn=lambda: current,
        cursor_reader=lambda: next(cursor_positions),
        input_tick_reader=lambda: 1000,
    )

    monitor.poll()
    current = current + timedelta(minutes=5)
    snapshot = monitor.poll()

    assert snapshot.had_new_activity is True
    assert snapshot.last_activity_at == current


def test_last_input_tick_change_marks_new_activity() -> None:
    current = datetime(2026, 6, 9, 9, 0, tzinfo=timezone(timedelta(hours=10)))
    input_ticks = iter([1000, 2000])
    monitor = UserActivityMonitor(
        clock_fn=lambda: current,
        cursor_reader=lambda: (100, 100),
        input_tick_reader=lambda: next(input_ticks),
    )

    monitor.poll()
    current = current + timedelta(minutes=1)
    snapshot = monitor.poll()

    assert snapshot.had_new_activity is True
    assert snapshot.last_activity_at == current