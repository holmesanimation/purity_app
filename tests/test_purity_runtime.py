"""Tests for purity_app runtime creation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from purity_app.services.runtime import PurityRuntime, create_purity_runtime
from purity_app.services.supervisor_client import PuritySupervisorClient

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@pytest.fixture()
def runtime(tmp_path: Path) -> PurityRuntime:
    return create_purity_runtime(tmp_path)


class TestPurityRuntime:
    def test_run_id_is_uuid(self, runtime: PurityRuntime) -> None:
        assert _UUID4_RE.match(runtime.session.run_id), (
            f"run_id {runtime.session.run_id!r} is not a valid UUID4"
        )

    def test_session_app_id(self, runtime: PurityRuntime) -> None:
        assert runtime.session.app_id == "purity_app"

    def test_heartbeat_dir_matches_supervisor_client(
        self, runtime: PurityRuntime, tmp_path: Path
    ) -> None:
        expected = PuritySupervisorClient(tmp_path).heartbeats_dir
        assert runtime.heartbeat._heartbeats_dir == expected

    def test_journal_service_configured(self, runtime: PurityRuntime) -> None:
        assert runtime.journal.cfg.run_id == runtime.session.run_id

    def test_tail_writer_path_under_system_root(self, runtime: PurityRuntime) -> None:
        assert "purity" in str(runtime.tail.path)
