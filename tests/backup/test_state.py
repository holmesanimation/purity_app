from __future__ import annotations

from pathlib import Path

from services.backup.models import BackupRunResult, FamilyResult, ManifestEntry, RunStatus
from services.backup.state import (
    append_run,
    load_manifest,
    load_state,
    manifest_path,
    save_manifest,
    state_path,
)


def _result(run_id: str) -> BackupRunResult:
    return BackupRunResult(
        run_id=run_id,
        started_at="2026-09-15T00:00:00+00:00",
        completed_at="2026-09-15T00:00:05+00:00",
        status=RunStatus.SUCCESS,
        file_count=3,
        verified_count=3,
        failed_count=0,
        bytes_copied=1234,
        last_error=None,
        family_results=[FamilyResult(family_name="notes", files_verified=3)],
    )


def test_load_state_returns_empty_when_missing(tmp_path: Path) -> None:
    assert load_state(tmp_path) == []


def test_append_run_persists_and_round_trips(tmp_path: Path) -> None:
    result = _result("run-1")

    append_run(tmp_path, result)

    history = load_state(tmp_path)
    assert len(history) == 1
    assert history[0].run_id == "run-1"
    assert history[0].status == RunStatus.SUCCESS
    assert history[0].family_results[0].family_name == "notes"
    assert state_path(tmp_path).exists()


def test_append_run_bounds_history_length(tmp_path: Path) -> None:
    for i in range(5):
        append_run(tmp_path, _result(f"run-{i}"), max_history=3)

    history = load_state(tmp_path)
    assert [r.run_id for r in history] == ["run-2", "run-3", "run-4"]


def test_load_manifest_returns_empty_when_missing(tmp_path: Path) -> None:
    assert load_manifest(tmp_path) == {}


def test_save_manifest_round_trips(tmp_path: Path) -> None:
    manifest = {
        "notes/purity.jsonl": ManifestEntry(
            content_hash="abc123", size=42, verified_at="2026-09-15T00:00:00+00:00"
        ),
    }

    save_manifest(tmp_path, manifest)

    reloaded = load_manifest(tmp_path)
    assert reloaded == manifest
    assert manifest_path(tmp_path).exists()
