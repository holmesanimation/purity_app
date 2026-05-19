"""Purity-app journal event emitters.

Each function emits a single typed event via the JournalService.
All payloads are plain dicts — no domain objects cross this boundary.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from services.journaling_profile import (
    KIND_SYSTEM_START,
    KIND_SYSTEM_STOP,
    KIND_SYSTEM_ALIVE,
    KIND_CHROME_OPENED,
    KIND_CHROME_ALLOWED,
    KIND_CHROME_BLOCKED,
    KIND_POPUP_TRIGGERED,
    KIND_NOTE_CREATED,
    KIND_REVIEW_OPENED,
)

if TYPE_CHECKING:
    from shane_common.journaling.service import JournalService


def emit_app_started(
    j: "JournalService",
    *,
    pid: int,
    argv: list,
    data_root: str,
) -> None:
    j.emit(
        KIND_SYSTEM_START,
        {"pid": pid, "argv": list(argv), "data_root": str(data_root)},
        source="app",
    )


def emit_app_stopped(
    j: "JournalService",
    *,
    reason: str = "normal",
) -> None:
    j.emit(KIND_SYSTEM_STOP, {"reason": reason}, source="app")


def emit_system_alive(j: "JournalService") -> None:
    j.emit(KIND_SYSTEM_ALIVE, {}, source="app")


def emit_chrome_opened(
    j: "JournalService",
    *,
    pid_count: int,
) -> None:
    j.emit(KIND_CHROME_OPENED, {"pid_count": pid_count}, source="chrome_watcher")


def emit_chrome_decision(
    j: "JournalService",
    *,
    allowed: bool,
    choice: str = "",
    reason: str = "",
) -> None:
    kind = KIND_CHROME_ALLOWED if allowed else KIND_CHROME_BLOCKED
    j.emit(
        kind,
        {"allowed": bool(allowed), "choice": str(choice), "reason": str(reason)},
        source="chrome_watcher",
    )


def emit_popup_triggered(
    j: "JournalService",
    *,
    popup_type: str,
) -> None:
    j.emit(KIND_POPUP_TRIGGERED, {"popup_type": popup_type}, source="popup_manager")


def emit_note_created(
    j: "JournalService",
    *,
    owner: str,
) -> None:
    j.emit(KIND_NOTE_CREATED, {"owner": owner}, source="notes")


def emit_review_opened(j: "JournalService") -> None:
    j.emit(KIND_REVIEW_OPENED, {}, source="review")
