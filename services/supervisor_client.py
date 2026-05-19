"""
PuritySupervisorClient — lightweight read/write adapter for the purity_app
watchdog state.

Wraps:
- HeartbeatReader  (reads purity_app.heartbeat.json)
- AppendOnlyAuditLog  (appends purity.audit.jsonl)

Default paths under *data_root*:
  _system/purity/heartbeats/   — heartbeat files
  _system/purity/audit/        — JSONL audit log
"""
from __future__ import annotations

from pathlib import Path

from shane_common.watchdog.audit import AppendOnlyAuditLog
from shane_common.watchdog.heartbeat_reader import HeartbeatReader


_DEFAULT_STALE_S = 10.0
_DEFAULT_DEAD_S = 60.0


class PuritySupervisorClient:
    """
    Read-mostly client for purity_app liveness state.

    Parameters
    ----------
    data_root:
        Root data directory for purity_app (e.g. ``Path.home() / ".purity"``).
    stale_s / dead_s:
        Passed through to HeartbeatReader for liveness classification.
    """

    def __init__(
        self,
        data_root: Path,
        stale_s: float = _DEFAULT_STALE_S,
        dead_s: float = _DEFAULT_DEAD_S,
    ) -> None:
        self._data_root = data_root
        self._heartbeats_dir = data_root / "_system" / "purity" / "heartbeats"
        self._audit_path = data_root / "_system" / "purity" / "audit" / "purity.audit.jsonl"
        self._heartbeat_reader = HeartbeatReader(
            heartbeats_dir=self._heartbeats_dir,
            stale_s=stale_s,
            dead_s=dead_s,
        )
        self._audit_log = AppendOnlyAuditLog(self._audit_path)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def heartbeat_reader(self) -> HeartbeatReader:
        return self._heartbeat_reader

    @property
    def audit_log(self) -> AppendOnlyAuditLog:
        return self._audit_log

    @property
    def heartbeats_dir(self) -> Path:
        return self._heartbeats_dir

    @property
    def audit_path(self) -> Path:
        return self._audit_path
