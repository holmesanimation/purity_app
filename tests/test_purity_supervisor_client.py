"""
Tests for PuritySupervisorClient.

These tests run headless (no Qt needed) and only test the file I/O layer.
"""
import json
import time
from pathlib import Path

import pytest

from purity_app.services.supervisor_client import PuritySupervisorClient


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "purity_data"


@pytest.fixture()
def client(data_root: Path) -> PuritySupervisorClient:
    return PuritySupervisorClient(data_root)


class TestPuritySupervisorClient:
    def test_heartbeats_dir_path(self, client: PuritySupervisorClient, data_root: Path) -> None:
        expected = data_root / "_system" / "purity" / "heartbeats"
        assert client.heartbeats_dir == expected

    def test_audit_path(self, client: PuritySupervisorClient, data_root: Path) -> None:
        expected = data_root / "_system" / "purity" / "audit" / "purity.audit.jsonl"
        assert client.audit_path == expected

    def test_read_returns_none_when_no_heartbeat(self, client: PuritySupervisorClient) -> None:
        hb, mtime, exit_present = client.heartbeat_reader.read("purity_app")
        assert hb is None
        assert mtime is None
        assert exit_present is False

    def test_audit_append_and_read(self, client: PuritySupervisorClient) -> None:
        record = {"ts": time.time(), "event": "test_event", "app_id": "purity_app"}
        client.audit_log.append(record)
        lines = client.audit_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event"] == "test_event"

    def test_heartbeat_read_after_write(
        self, client: PuritySupervisorClient, data_root: Path
    ) -> None:
        """Write a heartbeat file and confirm HeartbeatReader can read it."""
        hb_dir = data_root / "_system" / "purity" / "heartbeats"
        hb_dir.mkdir(parents=True, exist_ok=True)
        hb_path = hb_dir / "purity_app.heartbeat.json"
        hb_path.write_text(
            json.dumps({
                "schema_version": 1,
                "app_id": "purity_app",
                "pid": 12345,
                "ts_wall_utc": time.time(),
                "seq": 1,
            }),
            encoding="utf-8",
        )
        _, mtime, exit_present = client.heartbeat_reader.read("purity_app")
        assert mtime is not None
        assert exit_present is False
        assert not client.heartbeat_reader.is_dead(mtime)
