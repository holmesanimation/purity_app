from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.backup.health import (
    is_recovery_drill_due,
    last_restore_attempt,
    last_successful_restore,
)


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_no_successful_drill_is_due() -> None:
    assert is_recovery_drill_due(None) is True


def test_recent_successful_drill_not_due() -> None:
    assert is_recovery_drill_due(_iso(5)) is False


def test_old_successful_drill_is_due() -> None:
    assert is_recovery_drill_due(_iso(31)) is True


def test_boundary_not_due() -> None:
    assert is_recovery_drill_due(_iso(29), interval_days=30) is False


def test_last_successful_restore_ignores_failed_attempts_after_success() -> None:
    runs = [
        {"destination": "dropbox", "status": "success", "completed_at": _iso(31)},
        {"destination": "dropbox", "status": "failed", "completed_at": _iso(1)},
    ]
    last = last_successful_restore(runs, "dropbox")
    assert last is not None
    assert last["completed_at"] == runs[0]["completed_at"]
    assert is_recovery_drill_due(last["completed_at"]) is True


def test_new_success_resets_due_state() -> None:
    runs = [
        {"destination": "dropbox", "status": "success", "completed_at": _iso(31)},
        {"destination": "dropbox", "status": "failed", "completed_at": _iso(2)},
        {"destination": "dropbox", "status": "success", "completed_at": _iso(0)},
    ]
    last = last_successful_restore(runs, "dropbox")
    assert last["completed_at"] == runs[-1]["completed_at"]
    assert is_recovery_drill_due(last["completed_at"]) is False


def test_independent_destinations() -> None:
    runs = [
        {"destination": "local", "status": "success", "completed_at": _iso(2)},
        {"destination": "dropbox", "status": "success", "completed_at": _iso(40)},
    ]
    local_last = last_successful_restore(runs, "local")
    dropbox_last = last_successful_restore(runs, "dropbox")
    assert is_recovery_drill_due(local_last["completed_at"]) is False
    assert is_recovery_drill_due(dropbox_last["completed_at"]) is True


def test_last_restore_attempt_includes_failures() -> None:
    runs = [
        {"destination": "local", "status": "success", "completed_at": _iso(31)},
        {"destination": "local", "status": "failed", "completed_at": _iso(1)},
    ]
    attempt = last_restore_attempt(runs, "local")
    assert attempt["status"] == "failed"
