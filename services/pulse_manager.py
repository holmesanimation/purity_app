from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from typing import Any, Callable

from shane_common.preferences.manager import SettingsManager

from services.journal_events import (
    emit_pulse_note_submitted,
    emit_pulse_prompted,
    emit_pulse_reach_out_clicked,
    emit_pulse_submitted,
)
from services.pulse_activity import UserActivityMonitor
from services.pulse_models import PendingPulse, PulseKind, PulseRecord, PulseSliders
from services.pulse_store import PulseStore


_DURATION_TO_MINUTES = {
    "5m": 5,
    "10m": 10,
    "30m": 30,
    "1h": 60,
    "2h": 120,
}


class PulseManager:
    def __init__(
        self,
        *,
        data_root,
        settings_manager: SettingsManager,
        activity_monitor: UserActivityMonitor,
        journal=None,
        now_fn: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._store = PulseStore(data_root)
        self._settings_manager = settings_manager
        self._activity_monitor = activity_monitor
        self._journal = journal
        self._now_fn = now_fn or (lambda: datetime.now().astimezone())
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))
        self._active_prompt: PendingPulse | None = None

    @property
    def active_prompt(self) -> PendingPulse | None:
        return self._active_prompt

    def create_manual_pulse(self) -> PendingPulse | None:
        if self._active_prompt is not None:
            return self._active_prompt

        now = self._now_fn()
        return self._create_pending_pulse(
            pulse_kind=PulseKind.MANUAL,
            now=now,
            is_repeat=False,
        )

    def poll_due_pulse(self) -> PendingPulse | None:
        if self._active_prompt is not None:
            return None

        snapshot = self._activity_monitor.poll()
        if not snapshot.had_new_activity or snapshot.last_activity_at is None:
            return None

        now = snapshot.last_activity_at
        day = now.date().isoformat()
        state = self._store.load_day(day)
        due_kind = self._due_kind_for(now)
        if due_kind is None:
            return None

        is_repeat = False
        if due_kind is PulseKind.MORNING and state.has_completed(PulseKind.MORNING):
            return None
        if due_kind is PulseKind.AFTERNOON and state.has_completed(PulseKind.AFTERNOON):
            return None
        if due_kind is PulseKind.EVENING:
            if state.next_evening_due_local_ts:
                next_due = datetime.fromisoformat(state.next_evening_due_local_ts)
                if now < next_due:
                    return None
                is_repeat = True
            elif state.evening_records():
                return None

        return self._create_pending_pulse(
            pulse_kind=due_kind,
            now=now,
            is_repeat=is_repeat,
        )

    def submit_pulse(
        self,
        *,
        pending: PendingPulse,
        sliders: PulseSliders,
        answers: dict[str, Any],
        note_text: str = "",
        reach_out_text: str = "",
        reach_out_sent: bool = False,
        evening_duration_choice: str | None = None,
    ) -> PulseRecord:
        submitted_at = self._now_fn().isoformat()
        record = PulseRecord(
            pulse_id=pending.pulse_id,
            pulse_kind=pending.pulse_kind,
            submitted_local_ts=submitted_at,
            prompted_local_ts=pending.prompted_local_ts,
            sliders=sliders,
            answers=answers,
            note_text=note_text,
            reach_out_text=reach_out_text,
            reach_out_sent=reach_out_sent,
            evening_duration_choice=evening_duration_choice,
        )
        self._store.append_record(pending.day, record)
        if pending.pulse_kind is PulseKind.EVENING:
            next_due = self._next_evening_due(submitted_at, evening_duration_choice)
            self._store.update_prompt_state(
                pending.day,
                next_evening_due_local_ts=next_due,
            )
        if self._journal is not None:
            emit_pulse_submitted(
                self._journal,
                pulse_id=pending.pulse_id,
                pulse_kind=pending.pulse_kind.value,
                reached_out=reach_out_sent,
            )
        self._active_prompt = None
        return record

    def submit_note(self, *, pulse_id: str, pulse_kind: PulseKind) -> None:
        if self._journal is None:
            return
        emit_pulse_note_submitted(
            self._journal,
            pulse_id=pulse_id,
            pulse_kind=pulse_kind.value,
        )

    def record_reach_out(self, *, pulse_id: str, pulse_kind: PulseKind) -> None:
        if self._journal is None:
            return
        emit_pulse_reach_out_clicked(
            self._journal,
            pulse_id=pulse_id,
            pulse_kind=pulse_kind.value,
        )

    def _due_kind_for(self, now: datetime) -> PulseKind | None:
        morning_at = self._combine_day_time(now, self._time_setting("morning_time"))
        afternoon_at = self._combine_day_time(now, self._time_setting("afternoon_time"))
        evening_at = self._combine_day_time(now, self._time_setting("evening_start_time"))

        if now < morning_at:
            return None
        if now < afternoon_at:
            return PulseKind.MORNING
        if now < evening_at:
            return PulseKind.AFTERNOON
        return PulseKind.EVENING

    def _create_pending_pulse(
        self,
        *,
        pulse_kind: PulseKind,
        now: datetime,
        is_repeat: bool,
    ) -> PendingPulse:
        pending = PendingPulse(
            pulse_id=self._id_factory(),
            pulse_kind=pulse_kind,
            day=now.date().isoformat(),
            prompted_local_ts=now.isoformat(),
            is_repeat=is_repeat,
        )
        self._active_prompt = pending
        self._store.update_prompt_state(
            pending.day,
            pulse_kind=pending.pulse_kind.value,
            prompted_local_ts=pending.prompted_local_ts,
            last_activity_local_ts=now.isoformat(),
        )
        if self._journal is not None:
            emit_pulse_prompted(
                self._journal,
                pulse_id=pending.pulse_id,
                pulse_kind=pending.pulse_kind.value,
            )
        return pending

    def _time_setting(self, key: str) -> time:
        raw = str(self._settings_manager.get("app.pulse", key))
        return time.fromisoformat(raw)

    @staticmethod
    def _combine_day_time(now: datetime, value: time) -> datetime:
        return datetime.combine(now.date(), value, tzinfo=now.tzinfo)

    @staticmethod
    def _next_evening_due(submitted_at_iso: str, duration_choice: str | None) -> str | None:
        if duration_choice is None:
            return None
        submitted_at = datetime.fromisoformat(submitted_at_iso)
        minutes = _DURATION_TO_MINUTES[duration_choice]
        return (submitted_at + timedelta(minutes=minutes)).isoformat()