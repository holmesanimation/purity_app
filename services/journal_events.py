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
    KIND_PANIC_STARTED,
    KIND_PANIC_STATE_CHANGED,
    KIND_PANIC_REASONS_SELECTED,
    KIND_PANIC_REFLECTION_SAVED,
    KIND_PANIC_TOPIC_ACKNOWLEDGED,
    KIND_PANIC_COUNTDOWN_STARTED,
    KIND_PANIC_COUNTDOWN_COMPLETED,
    KIND_PANIC_CLOSED,
    KIND_PANIC_NOTIFY_GROUP_CLICKED,
    KIND_PANIC_DANGER_ELEVATED,
    KIND_PANIC_DANGER_CLEARED,
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


# ---------------------------------------------------------------------------
# Panic intervention emitters
# ---------------------------------------------------------------------------

def _panic_correlation(panic_session_id: str) -> dict:
    return {"panic_session_id": panic_session_id}


def emit_panic_started(
    j: "JournalService",
    *,
    panic_session_id: str,
    started_while_elevated: bool,
) -> None:
    j.emit(
        KIND_PANIC_STARTED,
        {
            "panic_session_id": panic_session_id,
            "started_while_elevated": bool(started_while_elevated),
        },
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )


def emit_panic_state_changed(
    j: "JournalService",
    *,
    panic_session_id: str,
    from_state: str,
    to_state: str,
) -> None:
    j.emit(
        KIND_PANIC_STATE_CHANGED,
        {
            "panic_session_id": panic_session_id,
            "from_state": from_state,
            "to_state": to_state,
        },
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )


def emit_panic_reasons_selected(
    j: "JournalService",
    *,
    panic_session_id: str,
    reason_ids: list[str],
) -> None:
    j.emit(
        KIND_PANIC_REASONS_SELECTED,
        {
            "panic_session_id": panic_session_id,
            "reason_ids": list(reason_ids),
        },
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )


def emit_panic_reflection_saved(
    j: "JournalService",
    *,
    panic_session_id: str,
    reason_id: str,
) -> None:
    j.emit(
        KIND_PANIC_REFLECTION_SAVED,
        {
            "panic_session_id": panic_session_id,
            "reason_id": reason_id,
        },
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )


def emit_panic_topic_acknowledged(
    j: "JournalService",
    *,
    panic_session_id: str,
    reason_id: str,
) -> None:
    j.emit(
        KIND_PANIC_TOPIC_ACKNOWLEDGED,
        {
            "panic_session_id": panic_session_id,
            "reason_id": reason_id,
        },
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )


def emit_panic_countdown_started(
    j: "JournalService",
    *,
    panic_session_id: str,
    countdown_seconds: int,
) -> None:
    j.emit(
        KIND_PANIC_COUNTDOWN_STARTED,
        {
            "panic_session_id": panic_session_id,
            "countdown_seconds": int(countdown_seconds),
        },
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )


def emit_panic_countdown_completed(
    j: "JournalService",
    *,
    panic_session_id: str,
) -> None:
    j.emit(
        KIND_PANIC_COUNTDOWN_COMPLETED,
        {"panic_session_id": panic_session_id},
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )


def emit_panic_closed(
    j: "JournalService",
    *,
    panic_session_id: str,
    outcome: str,
) -> None:
    j.emit(
        KIND_PANIC_CLOSED,
        {
            "panic_session_id": panic_session_id,
            "outcome": outcome,
        },
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )


def emit_panic_notify_group_clicked(
    j: "JournalService",
    *,
    panic_session_id: str,
) -> None:
    j.emit(
        KIND_PANIC_NOTIFY_GROUP_CLICKED,
        {"panic_session_id": panic_session_id},
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )


def emit_panic_danger_elevated(
    j: "JournalService",
    *,
    panic_session_id: str,
    override_url: str = "",
) -> None:
    j.emit(
        KIND_PANIC_DANGER_ELEVATED,
        {
            "panic_session_id": panic_session_id,
            "override_url": override_url,
        },
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )


def emit_panic_danger_cleared(
    j: "JournalService",
    *,
    panic_session_id: str,
) -> None:
    j.emit(
        KIND_PANIC_DANGER_CLEARED,
        {"panic_session_id": panic_session_id},
        source="panic",
        correlation=_panic_correlation(panic_session_id),
    )

