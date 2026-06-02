from __future__ import annotations

import os
from pathlib import Path

import app as app_module


class _FakeHeartbeatReader:
    def __init__(self, heartbeat, mtime, exit_present, *, dead=False, stale=False):
        self._heartbeat = heartbeat
        self._mtime = mtime
        self._exit_present = exit_present
        self._dead = dead
        self._stale = stale

    def read(self, app_id: str):
        assert app_id == "purity_app"
        return self._heartbeat, self._mtime, self._exit_present

    def is_dead(self, mtime) -> bool:
        assert mtime == self._mtime
        return self._dead

    def is_stale(self, mtime) -> bool:
        assert mtime == self._mtime
        return self._stale


class _FakeSupervisorClient:
    def __init__(self, data_root: Path, reader: _FakeHeartbeatReader):
        self.data_root = data_root
        self.heartbeat_reader = reader
        self.heartbeats_dir = data_root / "_system" / "purity" / "heartbeats"


def _install_fake_client(monkeypatch, reader: _FakeHeartbeatReader) -> None:
    def _factory(data_root: Path):
        return _FakeSupervisorClient(data_root, reader)

    monkeypatch.setattr(
        "services.supervisor_client.PuritySupervisorClient",
        _factory,
    )


class TestSingleInstanceDetection:
    def test_returns_none_when_no_heartbeat(self, monkeypatch, tmp_path: Path) -> None:
        reader = _FakeHeartbeatReader(None, None, False)
        _install_fake_client(monkeypatch, reader)

        assert app_module._find_running_instance(tmp_path) is None

    def test_returns_none_when_exit_marker_present(self, monkeypatch, tmp_path: Path) -> None:
        reader = _FakeHeartbeatReader({"pid": 123}, 10.0, True)
        _install_fake_client(monkeypatch, reader)

        assert app_module._find_running_instance(tmp_path) is None

    def test_returns_none_when_heartbeat_is_dead_and_pid_gone(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        # Dead heartbeat + dead PID → not running.
        reader = _FakeHeartbeatReader({"pid": 123}, 10.0, False, dead=True)
        _install_fake_client(monkeypatch, reader)
        monkeypatch.setattr(app_module, "_is_pid_running", lambda pid: False)

        assert app_module._find_running_instance(tmp_path) is None

    def test_detects_running_instance_when_heartbeat_is_dead_but_pid_alive(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        # Dead heartbeat mtime + live PID → still treat as running (startup race window:
        # new app deleted exit marker and wrote initial heartbeat but the background thread
        # hasn't refreshed the file yet when a duplicate launch checks).
        reader = _FakeHeartbeatReader({"pid": 123}, 10.0, False, dead=True)
        _install_fake_client(monkeypatch, reader)
        monkeypatch.setattr(app_module, "_is_pid_running", lambda pid: True)

        result = app_module._find_running_instance(tmp_path)
        assert result is not None
        assert result["pid"] == 123
        assert result["state"] == "stale"

    def test_returns_none_when_pid_is_not_running(self, monkeypatch, tmp_path: Path) -> None:
        reader = _FakeHeartbeatReader({"pid": 123}, 10.0, False)
        _install_fake_client(monkeypatch, reader)
        monkeypatch.setattr(app_module, "_is_pid_running", lambda pid: False)

        assert app_module._find_running_instance(tmp_path) is None

    def test_detects_running_instance(self, monkeypatch, tmp_path: Path) -> None:
        reader = _FakeHeartbeatReader({"pid": 4321}, 10.0, False)
        _install_fake_client(monkeypatch, reader)
        monkeypatch.setattr(app_module, "_is_pid_running", lambda pid: True)

        assert app_module._find_running_instance(tmp_path) == {
            "pid": 4321,
            "state": "running",
        }

    def test_detects_stale_running_instance(self, monkeypatch, tmp_path: Path) -> None:
        reader = _FakeHeartbeatReader({"pid": 4321}, 10.0, False, stale=True)
        _install_fake_client(monkeypatch, reader)
        monkeypatch.setattr(app_module, "_is_pid_running", lambda pid: True)

        assert app_module._find_running_instance(tmp_path) == {
            "pid": 4321,
            "state": "stale",
        }

    def test_detects_running_instance_even_with_stale_exit_marker(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        hb_dir = tmp_path / "_system" / "purity" / "heartbeats"
        hb_dir.mkdir(parents=True)
        exit_marker = hb_dir / "purity_app.exit_marker.json"
        exit_marker.write_text("{}", encoding="utf-8")

        reader = _FakeHeartbeatReader({"pid": 4321}, 10.0, True)
        _install_fake_client(monkeypatch, reader)
        monkeypatch.setattr(app_module, "_is_pid_running", lambda pid: True)
        os.utime(exit_marker, (5.0, 5.0))

        assert app_module._find_running_instance(tmp_path) == {
            "pid": 4321,
            "state": "running",
        }