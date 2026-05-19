"""Purity-app journal profile — kind taxonomy, stream routing, and disk layout."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from shane_common.journaling.profile import JournalProfile

# ---------------------------------------------------------------------------
# Kind constants
# ---------------------------------------------------------------------------

KIND_SYSTEM_START    = "system.start"
KIND_SYSTEM_STOP     = "system.stop"
KIND_SYSTEM_ALIVE    = "system.alive"
KIND_CHROME_OPENED   = "chrome.opened"
KIND_CHROME_ALLOWED  = "chrome.allowed"
KIND_CHROME_BLOCKED  = "chrome.blocked"
KIND_POPUP_TRIGGERED = "popup.triggered"
KIND_NOTE_CREATED    = "note.created"
KIND_REVIEW_OPENED   = "review.opened"

_PURITY_KINDS: frozenset = frozenset({
    KIND_SYSTEM_START,
    KIND_SYSTEM_STOP,
    KIND_SYSTEM_ALIVE,
    KIND_CHROME_OPENED,
    KIND_CHROME_ALLOWED,
    KIND_CHROME_BLOCKED,
    KIND_POPUP_TRIGGERED,
    KIND_NOTE_CREATED,
    KIND_REVIEW_OPENED,
})


def _local_date_from_local_ts(local_ts: str) -> str:
    """Extract the local YYYY-MM-DD from a local_TS ISO-8601 string."""
    try:
        return datetime.datetime.fromisoformat(local_ts).date().isoformat()
    except Exception:
        return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class PurityJournalProfile(JournalProfile):
    """
    Journal profile for purity_app.

    Disk layout::
        <data_root>/_system/purity/journals/<YYYY-MM-DD>/<stream>.jsonl

    Uses the local date from ``envelope["local_TS"]`` so journal directories
    match the user's wall-clock day rather than UTC midnight.
    """

    def __init__(self, data_root: Path) -> None:
        self._data_root = Path(data_root)

    def validate_kind(self, kind: str) -> Optional[str]:
        if kind not in _PURITY_KINDS:
            return f"Unknown purity kind: {kind!r}. Allowed: {sorted(_PURITY_KINDS)}"
        return None

    def stream_for_kind(self, kind: str) -> str:
        return kind.split(".")[0] if "." in kind else "misc"

    def route_event(self, envelope: dict) -> Path:
        local_ts = envelope.get("local_TS") or ""
        day = _local_date_from_local_ts(local_ts) if local_ts else datetime.date.today().isoformat()
        stream = self.stream_for_kind(str(envelope.get("kind") or "misc"))
        return (
            self._data_root
            / "_system"
            / "purity"
            / "journals"
            / day
            / f"{stream}.jsonl"
        )
