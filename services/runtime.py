"""Purity-app runtime — session identity, journaling, tail writer, and heartbeat."""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path

from shane_common.journaling.jsonl_sink import JsonlJournalSink, JsonlJournalSinkConfig
from shane_common.journaling.service import JournalConfig, JournalService
from shane_common.sessions.app_session import AppSession, make_app_session
from shane_common.sessions.tail_writer import SessionTailWriter
from shane_common.watchdog.heartbeat_writer import HeartbeatWriter

from services.journaling_profile import PurityJournalProfile


@dataclass
class PurityRuntime:
    session: AppSession
    journal: JournalService
    tail: SessionTailWriter
    heartbeat: HeartbeatWriter
    data_root: Path


def create_purity_runtime(data_root: Path) -> PurityRuntime:
    """
    Bootstrap the purity_app runtime objects.

    All paths are rooted under *data_root* (default ``~/.purity``,
    override via ``PURITY_DATA_ROOT`` env var — set by the caller).
    """
    data_root = Path(data_root)
    system_root = data_root / "_system" / "purity"

    # Session identity
    session = make_app_session(
        app_id="purity_app",
        app_name="PurityApp",
        data_root=str(data_root),
        system_root=str(system_root),
    )

    # Journal profile + sink + service
    profile = PurityJournalProfile(data_root)
    sink = JsonlJournalSink(JsonlJournalSinkConfig(profile=profile, flush_each=True))
    cfg = JournalConfig(
        app_id="purity_app",
        app_name="PurityApp",
        run_id=session.run_id,
    )
    journal = JournalService(cfg, profile=profile, sinks=[sink])

    # Session tail writer — place beside the per-day journal files
    today = datetime.date.today().isoformat()
    journals_dir = system_root / "journals"
    tail = SessionTailWriter(
        system_root=str(system_root),
        run_id=session.run_id,
    )
    # Override default path to sit beside the per-day journals
    tail.path = journals_dir / today / f"run_tail.{session.run_id}.json"

    # Heartbeat writer
    heartbeat = HeartbeatWriter(
        app_id="purity_app",
        heartbeats_dir=system_root / "heartbeats",
    )

    return PurityRuntime(
        session=session,
        journal=journal,
        tail=tail,
        heartbeat=heartbeat,
        data_root=data_root,
    )
