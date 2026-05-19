"""Tests for purity_app startup journal events."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import List

import pytest

from purity_app.services.journal_events import (
    emit_app_started,
    emit_app_stopped,
    emit_system_alive,
)
from purity_app.services.runtime import PurityRuntime, create_purity_runtime


def _all_jsonl_lines(root: Path) -> List[dict]:
    """Collect all parsed JSON lines from every *.jsonl file under *root*."""
    lines = []
    for f in root.rglob("*.jsonl"):
        for raw in f.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if raw:
                lines.append(json.loads(raw))
    return lines


@pytest.fixture()
def runtime(tmp_path: Path) -> PurityRuntime:
    return create_purity_runtime(tmp_path)


class TestPurityStartupJournal:
    def test_emit_app_started_creates_system_start_line(
        self, runtime: PurityRuntime, tmp_path: Path
    ) -> None:
        emit_app_started(
            runtime.journal,
            pid=12345,
            argv=["app.py"],
            data_root=str(tmp_path),
        )
        runtime.journal.close_sinks()

        lines = _all_jsonl_lines(tmp_path)
        assert lines, "No JSONL lines written"
        start_lines = [l for l in lines if l.get("kind") == "system.start"]
        assert start_lines, "No system.start event found"
        event = start_lines[0]
        assert list(event.keys())[0] == "local_TS", "local_TS must be first key"
        assert event["run_id"] == runtime.session.run_id

    def test_emit_app_stopped_creates_system_stop_line(
        self, runtime: PurityRuntime, tmp_path: Path
    ) -> None:
        emit_app_stopped(runtime.journal, reason="test")
        runtime.journal.close_sinks()

        lines = _all_jsonl_lines(tmp_path)
        stop_lines = [l for l in lines if l.get("kind") == "system.stop"]
        assert stop_lines, "No system.stop event found"
        event = stop_lines[0]
        assert list(event.keys())[0] == "local_TS"

    def test_system_alive_kind(
        self, runtime: PurityRuntime, tmp_path: Path
    ) -> None:
        emit_system_alive(runtime.journal)
        runtime.journal.close_sinks()

        lines = _all_jsonl_lines(tmp_path)
        alive_lines = [l for l in lines if l.get("kind") == "system.alive"]
        assert alive_lines, "No system.alive event found"

    def test_run_tail_flush_creates_json_file(
        self, runtime: PurityRuntime
    ) -> None:
        runtime.tail.note_clock(time.time())
        runtime.tail.flush()

        assert runtime.tail.path.exists(), f"Tail file not found: {runtime.tail.path}"
        data = json.loads(runtime.tail.path.read_text(encoding="utf-8"))
        assert list(data.keys())[0] == "local_TS", "local_TS must be first key"
        assert data["run_id"] == runtime.session.run_id
