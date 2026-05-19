"""
Phase 0 characterization tests: JSONL log path naming and append behavior.
"""
import json
import datetime
import pytest
import reminder_dialog as rd


class TestGetLogPath:
    def test_returns_path_in_log_dir(self):
        path = rd.get_log_path()
        assert path.parent == rd.LOG_DIR

    def test_filename_matches_year_month_pattern(self, monkeypatch):
        fake_today = datetime.date(2026, 5, 18)
        monkeypatch.setattr(datetime, "date", type(
            "date", (datetime.date,), {"today": staticmethod(lambda: fake_today)}
        ))
        # Patch just enough to check the format.
        # get_log_path calls datetime.date.today() internally.
        path = rd.get_log_path()
        assert path.name.startswith("focus_guard_")
        assert path.name.endswith(".jsonl")

    def test_filename_contains_current_year_month(self):
        today = datetime.date.today()
        expected_suffix = f"{today:%Y_%m}.jsonl"
        path = rd.get_log_path()
        assert path.name.endswith(expected_suffix)


class TestAppendFocusLog:
    def test_creates_file_and_appends_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rd, "LOG_DIR", tmp_path)
        record = {"event": "test", "ts": "2026-05-18T00:00:00Z", "value": 42}
        rd.append_focus_log(record)

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        lines = files[0].read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed == record

    def test_appends_multiple_records_as_separate_lines(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rd, "LOG_DIR", tmp_path)
        rd.append_focus_log({"event": "first"})
        rd.append_focus_log({"event": "second"})
        rd.append_focus_log({"event": "third"})

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        lines = files[0].read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        events = [json.loads(l)["event"] for l in lines]
        assert events == ["first", "second", "third"]

    def test_creates_log_dir_if_missing(self, tmp_path, monkeypatch):
        new_dir = tmp_path / "nested" / "logs"
        monkeypatch.setattr(rd, "LOG_DIR", new_dir)
        rd.append_focus_log({"event": "dir_creation"})
        assert new_dir.exists()

    def test_record_is_single_line_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rd, "LOG_DIR", tmp_path)
        rd.append_focus_log({"event": "line_check", "nested": {"a": 1}})
        files = list(tmp_path.iterdir())
        content = files[0].read_text(encoding="utf-8")
        # Must end with newline
        assert content.endswith("\n")
        # Each line must be parseable
        for line in content.splitlines():
            json.loads(line)  # must not raise
