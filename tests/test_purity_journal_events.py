"""Tests for purity_app individual journal event emitters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest

from purity_app.services.journal_events import (
    emit_chrome_decision,
    emit_chrome_opened,
    emit_popup_triggered,
    emit_note_created,
    emit_app_started,
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


def _lines_for_kind(root: Path, kind: str) -> List[dict]:
    return [l for l in _all_jsonl_lines(root) if l.get("kind") == kind]


@pytest.fixture()
def runtime(tmp_path: Path) -> PurityRuntime:
    return create_purity_runtime(tmp_path)


class TestPurityJournalEvents:
    def test_chrome_opened_event(self, runtime: PurityRuntime, tmp_path: Path) -> None:
        emit_chrome_opened(runtime.journal, pid_count=3)
        runtime.journal.close_sinks()

        events = _lines_for_kind(tmp_path, "chrome.opened")
        assert events, "No chrome.opened event found"
        event = events[0]
        assert list(event.keys())[0] == "local_TS"
        assert event["payload"]["pid_count"] == 3

    def test_chrome_allowed_event(self, runtime: PurityRuntime, tmp_path: Path) -> None:
        emit_chrome_decision(
            runtime.journal,
            allowed=True,
            choice="Work",
            reason="Need to check a specific reference.",
        )
        runtime.journal.close_sinks()

        events = _lines_for_kind(tmp_path, "chrome.allowed")
        assert events, "No chrome.allowed event found"
        event = events[0]
        assert event["payload"]["allowed"] is True
        assert event["payload"]["choice"] == "Work"
        assert event["payload"]["reason"] == "Need to check a specific reference."

    def test_chrome_blocked_event(self, runtime: PurityRuntime, tmp_path: Path) -> None:
        emit_chrome_decision(
            runtime.journal,
            allowed=False,
            choice="Tempted",
            reason="",
        )
        runtime.journal.close_sinks()

        events = _lines_for_kind(tmp_path, "chrome.blocked")
        assert events, "No chrome.blocked event found"
        event = events[0]
        assert event["payload"]["allowed"] is False
        assert event["payload"]["choice"] == "Tempted"
        assert event["payload"]["reason"] == ""

    def test_popup_triggered_event(self, runtime: PurityRuntime, tmp_path: Path) -> None:
        emit_popup_triggered(runtime.journal, popup_type="prayer")
        runtime.journal.close_sinks()

        events = _lines_for_kind(tmp_path, "popup.triggered")
        assert events, "No popup.triggered event found"
        event = events[0]
        assert event["payload"]["popup_type"] == "prayer"

    def test_all_events_share_same_run_id(
        self, runtime: PurityRuntime, tmp_path: Path
    ) -> None:
        emit_app_started(runtime.journal, pid=1, argv=[], data_root=str(tmp_path))
        emit_system_alive(runtime.journal)
        runtime.journal.close_sinks()

        lines = _all_jsonl_lines(tmp_path)
        assert len(lines) >= 2
        run_ids = {l["run_id"] for l in lines if "run_id" in l}
        assert run_ids == {runtime.session.run_id}, (
            f"Expected single run_id {runtime.session.run_id!r}, got {run_ids}"
        )
