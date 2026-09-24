"""Weekly backup schedule: due-occurrence computation and durable state.

Hosted by a QTimer tick in ``app.py``. Pure functions below compute whether
a scheduled backup is due (inject ``now`` for testability); ``BackupScheduler``
is a thin QObject wrapper tying schedule settings + durable state to the
shared ``BackupController`` single-flight lock, so manual and scheduled runs
never overlap and each due occurrence executes exactly once.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PySide6.QtCore import QObject

from shane_common.io.atomic import write_json_atomic

from services.settings_schemas import (
    get_backup_schedule_enabled,
    get_backup_schedule_time,
    get_backup_schedule_timezone,
    get_backup_schedule_weekday,
    resolve_purity_data_root,
)

from .controller import BackupController
from .models import BackupRunResult

_SCHEDULE_STATE_RELATIVE_PATH = ("_system", "purity", "backup", "schedule_state.json")


@dataclass(frozen=True)
class BackupSchedule:
    """Weekly schedule, settings-backed.

    ``weekday`` follows ``datetime.weekday()`` (0=Monday .. 6=Sunday).
    ``timezone`` is an IANA name; empty string means "system local timezone".
    """

    enabled: bool
    weekday: int
    time: str
    timezone: str


@dataclass
class ScheduleState:
    last_evaluated_occurrence_id: str | None = None
    last_run_result_ref: str | None = None
    last_evaluated_dropbox_occurrence_id: str | None = None
    last_dropbox_run_result_ref: str | None = None

    def to_dict(self) -> dict:
        return {
            "last_evaluated_occurrence_id": self.last_evaluated_occurrence_id,
            "last_run_result_ref": self.last_run_result_ref,
            "last_evaluated_dropbox_occurrence_id": self.last_evaluated_dropbox_occurrence_id,
            "last_dropbox_run_result_ref": self.last_dropbox_run_result_ref,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduleState":
        return cls(
            last_evaluated_occurrence_id=data.get("last_evaluated_occurrence_id"),
            last_run_result_ref=data.get("last_run_result_ref"),
            last_evaluated_dropbox_occurrence_id=data.get("last_evaluated_dropbox_occurrence_id"),
            last_dropbox_run_result_ref=data.get("last_dropbox_run_result_ref"),
        )


def schedule_state_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*_SCHEDULE_STATE_RELATIVE_PATH)


def load_schedule_state(data_root: Path) -> ScheduleState:
    path = schedule_state_path(data_root)
    if not path.exists():
        return ScheduleState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        traceback.print_exc()
        return ScheduleState()
    return ScheduleState.from_dict(raw if isinstance(raw, dict) else {})


def save_schedule_state(data_root: Path, state: ScheduleState) -> None:
    write_json_atomic(schedule_state_path(data_root), state.to_dict())


def load_schedule(settings_manager) -> BackupSchedule:
    return BackupSchedule(
        enabled=get_backup_schedule_enabled(settings_manager),
        weekday=get_backup_schedule_weekday(settings_manager),
        time=get_backup_schedule_time(settings_manager),
        timezone=get_backup_schedule_timezone(settings_manager),
    )


def _tzinfo(schedule: BackupSchedule):
    if schedule.timezone:
        return ZoneInfo(schedule.timezone)
    return datetime.now().astimezone().tzinfo


def _parse_time(raw: str) -> tuple[int, int]:
    hour_str, minute_str = raw.split(":", 1)
    return int(hour_str), int(minute_str)


def last_occurrence_at_or_before(now: datetime, schedule: BackupSchedule) -> datetime:
    """The most recent scheduled wall-clock datetime at or before ``now``.

    ``now`` must be timezone-aware.
    """
    tz = _tzinfo(schedule)
    local_now = now.astimezone(tz)
    hour, minute = _parse_time(schedule.time)
    days_since = (local_now.weekday() - schedule.weekday) % 7
    candidate = (local_now - timedelta(days=days_since)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    if candidate > local_now:
        candidate -= timedelta(days=7)
    return candidate


def occurrence_id(occurrence: datetime) -> str:
    return occurrence.isoformat()


def is_due(now: datetime, schedule: BackupSchedule, state: ScheduleState) -> str | None:
    """Return the occurrence_id of a due, not-yet-started occurrence, else None."""
    if not schedule.enabled:
        return None
    occurrence = last_occurrence_at_or_before(now, schedule)
    occ_id = occurrence_id(occurrence)
    if occ_id == state.last_evaluated_occurrence_id:
        return None
    return occ_id


def is_due_for_dropbox(now: datetime, schedule: BackupSchedule, state: ScheduleState) -> str | None:
    """Same weekly schedule as local, but tracked with its own occurrence dedup
    so a Dropbox failure/retry never interferes with the local run's state.
    """
    if not schedule.enabled:
        return None
    occurrence = last_occurrence_at_or_before(now, schedule)
    occ_id = occurrence_id(occurrence)
    if occ_id == state.last_evaluated_dropbox_occurrence_id:
        return None
    return occ_id


class BackupScheduler(QObject):
    """Ties schedule settings + durable state to the shared ``BackupController``.

    ``check_now()`` is hosted by an ``app.py`` QTimer tick and is safe to call
    frequently: it only starts a run when a new occurrence is due, and shares
    the single-flight lock with manual runs so it never double-runs.
    """

    def __init__(
        self,
        settings_manager,
        controller: BackupController,
        parent: QObject | None = None,
        *,
        dropbox_controller: "DropboxController | None" = None,
    ) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager
        self._controller = controller
        self._dropbox_controller = dropbox_controller
        self._data_root = resolve_purity_data_root(settings_manager)
        self._pending_occurrence_id: str | None = None
        self._pending_dropbox_occurrence_id: str | None = None
        self._controller.run_finished.connect(self._on_run_finished)
        if self._dropbox_controller is not None:
            self._dropbox_controller.run_finished.connect(self._on_dropbox_run_finished)

    def check_now(self, now: datetime | None = None) -> None:
        now = now or datetime.now().astimezone()
        schedule = load_schedule(self._settings_manager)
        state = load_schedule_state(self._data_root)

        occ_id = is_due(now, schedule, state)
        if occ_id is not None:
            started = self._controller.back_up_now()
            if started:
                self._pending_occurrence_id = occ_id
                state.last_evaluated_occurrence_id = occ_id
                save_schedule_state(self._data_root, state)
            # rejection (no destination / already running) leaves it due for next tick

        if self._dropbox_controller is not None:
            state = load_schedule_state(self._data_root)
            dropbox_occ_id = is_due_for_dropbox(now, schedule, state)
            if dropbox_occ_id is not None:
                started = self._dropbox_controller.back_up_now()
                if started:
                    self._pending_dropbox_occurrence_id = dropbox_occ_id
                    state.last_evaluated_dropbox_occurrence_id = dropbox_occ_id
                    save_schedule_state(self._data_root, state)
                # rejection (not ready / already running) leaves it due for next tick

    def _on_run_finished(self, result: BackupRunResult) -> None:
        if self._pending_occurrence_id is None:
            return
        state = load_schedule_state(self._data_root)
        state.last_run_result_ref = result.run_id
        save_schedule_state(self._data_root, state)
        self._pending_occurrence_id = None

    def _on_dropbox_run_finished(self, result: BackupRunResult) -> None:
        if self._pending_dropbox_occurrence_id is None:
            return
        state = load_schedule_state(self._data_root)
        state.last_dropbox_run_result_ref = result.run_id
        save_schedule_state(self._data_root, state)
        self._pending_dropbox_occurrence_id = None
