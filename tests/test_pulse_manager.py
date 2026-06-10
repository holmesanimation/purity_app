from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.pulse_activity import ActivitySnapshot
from services.pulse_manager import PulseManager
from services.pulse_models import PulseKind, PulseSliders
from services.settings_schemas import build_purity_settings_manager


class _FakeActivityMonitor:
    def __init__(self, snapshots: list[ActivitySnapshot]) -> None:
        self._snapshots = list(snapshots)

    def poll(self) -> ActivitySnapshot:
        if not self._snapshots:
            raise AssertionError("No activity snapshots left for PulseManager test.")
        return self._snapshots.pop(0)


def _local_dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 9, hour, minute, tzinfo=timezone(timedelta(hours=10)))


def test_morning_pulse_requires_new_activity_after_morning_time(tmp_path) -> None:
    settings = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    monitor = _FakeActivityMonitor(
        [
            ActivitySnapshot(had_new_activity=False, last_activity_at=None),
            ActivitySnapshot(had_new_activity=True, last_activity_at=_local_dt(9, 5)),
        ]
    )
    manager = PulseManager(
        data_root=tmp_path,
        settings_manager=settings,
        activity_monitor=monitor,
        now_fn=lambda: _local_dt(9, 5),
        id_factory=lambda: "pulse-morning",
    )

    assert manager.poll_due_pulse() is None
    pending = manager.poll_due_pulse()

    assert pending is not None
    assert pending.pulse_kind is PulseKind.MORNING
    assert pending.pulse_id == "pulse-morning"


def test_morning_is_skipped_once_first_activity_happens_in_afternoon_window(tmp_path) -> None:
    settings = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    monitor = _FakeActivityMonitor(
        [ActivitySnapshot(had_new_activity=True, last_activity_at=_local_dt(14, 5))]
    )
    manager = PulseManager(
        data_root=tmp_path,
        settings_manager=settings,
        activity_monitor=monitor,
        now_fn=lambda: _local_dt(14, 5),
        id_factory=lambda: "pulse-afternoon",
    )

    pending = manager.poll_due_pulse()

    assert pending is not None
    assert pending.pulse_kind is PulseKind.AFTERNOON


def test_evening_repeat_waits_until_selected_duration_has_elapsed_and_activity_returns(tmp_path) -> None:
    settings = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    first_now = _local_dt(21, 5)
    second_now = first_now + timedelta(minutes=20)
    third_now = first_now + timedelta(minutes=35)
    monitor = _FakeActivityMonitor(
        [
            ActivitySnapshot(had_new_activity=True, last_activity_at=first_now),
            ActivitySnapshot(had_new_activity=True, last_activity_at=second_now),
            ActivitySnapshot(had_new_activity=True, last_activity_at=third_now),
        ]
    )
    current_now = first_now
    manager = PulseManager(
        data_root=tmp_path,
        settings_manager=settings,
        activity_monitor=monitor,
        now_fn=lambda: current_now,
        id_factory=lambda: f"pulse-{current_now.hour}-{current_now.minute}",
    )

    first_pending = manager.poll_due_pulse()
    assert first_pending is not None
    assert first_pending.pulse_kind is PulseKind.EVENING

    manager.submit_pulse(
        pending=first_pending,
        sliders=PulseSliders(),
        answers={
            "what_are_you_doing_right_now": "Working late",
            "how_long_do_you_plan_to_keep_doing_it": "30m",
        },
        evening_duration_choice="30m",
    )

    current_now = second_now
    assert manager.poll_due_pulse() is None

    current_now = third_now
    second_pending = manager.poll_due_pulse()
    assert second_pending is not None
    assert second_pending.pulse_kind is PulseKind.EVENING
    assert second_pending.is_repeat is True


def test_active_prompt_is_not_duplicated_until_submission(tmp_path) -> None:
    settings = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    monitor = _FakeActivityMonitor(
        [
            ActivitySnapshot(had_new_activity=True, last_activity_at=_local_dt(9, 1)),
            ActivitySnapshot(had_new_activity=True, last_activity_at=_local_dt(9, 2)),
        ]
    )
    manager = PulseManager(
        data_root=tmp_path,
        settings_manager=settings,
        activity_monitor=monitor,
        now_fn=lambda: _local_dt(9, 2),
        id_factory=lambda: "pulse-single",
    )

    pending = manager.poll_due_pulse()
    duplicate = manager.poll_due_pulse()

    assert pending is not None
    assert duplicate is None


def test_manual_pulse_can_be_created_before_regular_times(tmp_path) -> None:
    settings = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    monitor = _FakeActivityMonitor([])
    now = _local_dt(8, 30)
    manager = PulseManager(
        data_root=tmp_path,
        settings_manager=settings,
        activity_monitor=monitor,
        now_fn=lambda: now,
        id_factory=lambda: "pulse-manual",
    )

    pending = manager.create_manual_pulse()

    assert pending is not None
    assert pending.pulse_id == "pulse-manual"
    assert pending.pulse_kind is PulseKind.MANUAL