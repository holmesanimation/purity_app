"""Tests for PanicStats aggregate store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from purity_app.services.panic_stats import PanicStats


class TestPanicStats:
    def test_initial_counts_are_zero(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        assert stats.get_count("lonely") == 0

    def test_record_single_reason_increments_count(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        stats.record_reasons(["lonely"])
        assert stats.get_count("lonely") == 1

    def test_record_multiple_reasons(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        stats.record_reasons(["lonely", "tired", "anxious"])
        assert stats.get_count("lonely") == 1
        assert stats.get_count("tired") == 1
        assert stats.get_count("anxious") == 1

    def test_count_increments_across_calls(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        stats.record_reasons(["lonely"])
        stats.record_reasons(["lonely"])
        stats.record_reasons(["lonely"])
        assert stats.get_count("lonely") == 3

    def test_persists_to_disk(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        stats.record_reasons(["tired", "lonely"])

        # Reload from disk
        stats2 = PanicStats(tmp_path)
        assert stats2.get_count("tired") == 1
        assert stats2.get_count("lonely") == 1

    def test_reload_preserves_increments(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        stats.record_reasons(["tired"])
        stats.record_reasons(["tired"])

        stats2 = PanicStats(tmp_path)
        stats2.record_reasons(["tired"])

        assert stats2.get_count("tired") == 3

    def test_get_top_reasons_order(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        stats.record_reasons(["anxious"])
        stats.record_reasons(["anxious"])
        stats.record_reasons(["lonely"])
        stats.record_reasons(["lonely"])
        stats.record_reasons(["lonely"])
        stats.record_reasons(["tired"])

        top = stats.get_top_reasons(3)
        assert top[0] == "lonely"
        assert top[1] == "anxious"
        assert top[2] == "tired"

    def test_get_top_reasons_n_capped(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        stats.record_reasons(["a", "b", "c", "d", "e"])
        top = stats.get_top_reasons(3)
        assert len(top) == 3

    def test_get_top_reasons_empty(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        assert stats.get_top_reasons(5) == []

    def test_reflection_text_never_stored(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        stats.record_reasons(["lonely"])

        disk_path = tmp_path / "data" / "panic" / "reason_counts.json"
        content = disk_path.read_text(encoding="utf-8")
        # Ensure no reflection-like keys are present
        parsed = json.loads(content)
        for reason_id, entry in parsed.items():
            assert set(entry.keys()) <= {"count", "last_seen_ts"}, (
                f"Unexpected keys in entry for {reason_id!r}: {set(entry.keys())}"
            )

    def test_last_seen_ts_updated(self, tmp_path: Path) -> None:
        import time
        stats = PanicStats(tmp_path)
        before = time.time()
        stats.record_reasons(["tired"])
        after = time.time()

        ts = stats._data["tired"]["last_seen_ts"]
        assert before <= ts <= after

    def test_json_file_location(self, tmp_path: Path) -> None:
        stats = PanicStats(tmp_path)
        stats.record_reasons(["lonely"])
        expected = tmp_path / "data" / "panic" / "reason_counts.json"
        assert expected.exists()
