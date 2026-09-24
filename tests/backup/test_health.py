"""Tests for services.backup.health — stale-backup detection (P5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.backup.health import is_stale, last_successful_run
from services.backup.models import BackupRunResult, RunStatus


def _run(status: RunStatus, completed_at: datetime) -> BackupRunResult:
    return BackupRunResult(
        run_id="r",
        started_at=completed_at.isoformat(),
        completed_at=completed_at.isoformat(),
        status=status,
        file_count=1,
        verified_count=1 if status == RunStatus.SUCCESS else 0,
        failed_count=0 if status == RunStatus.SUCCESS else 1,
        bytes_copied=0,
        last_error=None,
        family_results=[],
    )


def test_no_runs_is_stale():
    assert is_stale([], threshold_days=10) is True


def test_recent_success_not_stale():
    now = datetime.now(timezone.utc)
    runs = [_run(RunStatus.SUCCESS, now - timedelta(days=1))]
    assert is_stale(runs, threshold_days=10, now=now) is False


def test_old_success_is_stale():
    now = datetime.now(timezone.utc)
    runs = [_run(RunStatus.SUCCESS, now - timedelta(days=11))]
    assert is_stale(runs, threshold_days=10, now=now) is True


def test_only_failed_runs_is_stale():
    now = datetime.now(timezone.utc)
    runs = [_run(RunStatus.FAILED, now - timedelta(hours=1))]
    assert is_stale(runs, threshold_days=10, now=now) is True


def test_last_successful_run_ignores_trailing_failure():
    now = datetime.now(timezone.utc)
    runs = [
        _run(RunStatus.SUCCESS, now - timedelta(days=2)),
        _run(RunStatus.FAILED, now - timedelta(hours=1)),
    ]
    last = last_successful_run(runs)
    assert last is not None
    assert last.status == RunStatus.SUCCESS
    assert is_stale(runs, threshold_days=10, now=now) is False
