import json
import os
from pathlib import Path

from purity_app.services.web_requests import (
    is_purity_app_running,
    mark_web_launch_request_done,
    read_pending_web_launch_requests,
    request_inbox_dir,
    submit_web_launch_request,
)


def test_submit_web_launch_request_writes_inbox_file(tmp_path: Path) -> None:
    path = submit_web_launch_request(tmp_path, ["https://example.com"])

    assert path.parent == request_inbox_dir(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["args"] == ["https://example.com"]


def test_read_and_mark_pending_web_launch_requests(tmp_path: Path) -> None:
    submit_web_launch_request(tmp_path, ["https://example.com"])

    pending = read_pending_web_launch_requests(tmp_path)

    assert len(pending) == 1
    assert pending[0][1]["args"] == ["https://example.com"]

    mark_web_launch_request_done(pending[0][0])
    assert read_pending_web_launch_requests(tmp_path) == []


class _FakeHeartbeatReader:
    def __init__(self, heartbeat, mtime, exit_present, *, dead=False):
        self._heartbeat = heartbeat
        self._mtime = mtime
        self._exit_present = exit_present
        self._dead = dead
        self._heartbeats_dir = Path("C:/tmp/heartbeats")

    def read(self, app_id: str):
        assert app_id == "purity_app"
        return self._heartbeat, self._mtime, self._exit_present

    def is_dead(self, mtime):
        return self._dead


class _FakeSupervisorClient:
    def __init__(self, reader: _FakeHeartbeatReader):
        self.heartbeat_reader = reader
        self.heartbeats_dir = reader._heartbeats_dir


def test_running_check_ignores_stale_exit_marker(monkeypatch, tmp_path: Path) -> None:
    hb_dir = tmp_path / "_system" / "purity" / "heartbeats"
    hb_dir.mkdir(parents=True)
    exit_marker = hb_dir / "purity_app.exit_marker.json"
    exit_marker.write_text("{}", encoding="utf-8")

    reader = _FakeHeartbeatReader({"pid": 1234}, 10.0, True)
    reader._heartbeats_dir = hb_dir

    monkeypatch.setattr(
        "purity_app.services.web_requests.PuritySupervisorClient",
        lambda data_root: _FakeSupervisorClient(reader),
    )
    monkeypatch.setattr(
        "purity_app.services.web_requests._is_pid_running",
        lambda pid: True,
    )
    os.utime(exit_marker, (5.0, 5.0))

    assert is_purity_app_running(tmp_path) is True