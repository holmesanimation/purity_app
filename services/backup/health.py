"""Pure staleness checks for backup run history (no I/O, no Qt).

Grounded in a real P1-P4 gap: neither local nor Dropbox backup surfaced
any signal when the last successful run fell behind the weekly schedule.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import BackupRunResult, RunStatus


def last_successful_run(runs: list[BackupRunResult]) -> BackupRunResult | None:
    for run in reversed(runs):
        if run.status == RunStatus.SUCCESS:
            return run
    return None


def is_stale(
    runs: list[BackupRunResult], threshold_days: int, now: datetime | None = None
) -> bool:
    """True if there's no successful run, or the last one is older than the threshold."""
    last = last_successful_run(runs)
    if last is None:
        return True
    completed = last.completed_at or last.started_at
    try:
        completed_at = datetime.fromisoformat(completed)
    except ValueError:
        return True
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    age_days = (now - completed_at).total_seconds() / 86400.0
    return age_days > threshold_days


def last_successful_restore(runs: list[dict], destination: str) -> dict | None:
    """Latest ``restore_state.json`` entry for ``destination`` with status "success"."""
    for run in reversed(runs):
        if run.get("destination") == destination and run.get("status") == "success":
            return run
    return None


def last_restore_attempt(runs: list[dict], destination: str) -> dict | None:
    """Most recent ``restore_state.json`` entry for ``destination``, any status."""
    for run in reversed(runs):
        if run.get("destination") == destination:
            return run
    return None


def is_recovery_drill_due(
    last_successful_drill_at: str | None,
    now: datetime | None = None,
    interval_days: int = 30,
) -> bool:
    """True if no successful recovery drill has ever occurred, or the last one
    is older than ``interval_days``. Based on the last *successful* drill only
    — a later failed/partial attempt never resets or clears this due state.
    """
    if not last_successful_drill_at:
        return True
    try:
        completed_at = datetime.fromisoformat(last_successful_drill_at)
    except ValueError:
        return True
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    age_days = (now - completed_at).total_seconds() / 86400.0
    return age_days > interval_days
