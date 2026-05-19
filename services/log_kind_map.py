# purity_app/services/log_kind_map.py
"""Kind-spec map and viewer type taxonomy for purity_app journal events."""
from __future__ import annotations

from typing import Dict, Optional

from shane_common.ui.log_viewer.kind_spec import KindSpec, _DEFAULT_KIND_SPEC
from shane_common.ui.log_viewer.log_row import LogRow
from shane_common.ui.log_viewer.log_table_model import TYPE_ALL


TYPE_SYSTEM = 1 << 0
TYPE_WEB = 1 << 1
TYPE_INTERVENTION = 1 << 2
TYPE_NOTES = 1 << 3
TYPE_REVIEW = 1 << 4
TYPE_MISC = 1 << 5

PURITY_TYPE_LABELS: Dict[int, str] = {
    TYPE_SYSTEM: "System",
    TYPE_WEB: "Web",
    TYPE_INTERVENTION: "Intervention",
    TYPE_NOTES: "Notes",
    TYPE_REVIEW: "Review",
    TYPE_MISC: "Misc",
}

PURITY_TYPE_OPTIONS: list[tuple[str, int]] = [
    ("All", TYPE_ALL),
    ("System", TYPE_SYSTEM),
    ("Web", TYPE_WEB),
    ("Intervention", TYPE_INTERVENTION),
    ("Notes", TYPE_NOTES),
    ("Review", TYPE_REVIEW),
    ("Misc", TYPE_MISC),
]


def _chrome_allowed_message(payload: dict) -> str:
    choice = str(payload.get("choice") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    url = str(payload.get("url") or "").strip()
    subject = choice or url or "?"
    if reason:
        return f"Web allowed: {subject} - {reason}"
    return f"Web allowed: {subject}"


def _chrome_blocked_message(payload: dict) -> str:
    choice = str(payload.get("choice") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    url = str(payload.get("url") or "").strip()
    subject = choice or url or reason or "?"
    return f"Web blocked: {subject}"

PURITY_KIND_MAP: Dict[str, KindSpec] = {
    "system.start": KindSpec(
        severity="INFO",
        message_template="Purity started",
        importance="NORMAL",
    ),
    "system.stop": KindSpec(
        severity="INFO",
        message_template="Purity stopped",
        importance="NORMAL",
    ),
    "system.alive": KindSpec(
        severity="DEBUG",
        message_template="Alive tick",
        importance="LOW",
        dedupe_interval_s=86400.0,
    ),
    "chrome.opened": KindSpec(
        severity="INFO",
        message_template="Chrome opened",
        importance="NORMAL",
    ),
    "chrome.allowed": KindSpec(
        severity="INFO",
        message_template="Web allowed",
        message_fn=_chrome_allowed_message,
        importance="NORMAL",
    ),
    "chrome.blocked": KindSpec(
        severity="WARN",
        message_template="Web blocked",
        message_fn=_chrome_blocked_message,
        importance="HIGH",
        problem=True,
    ),
    "popup.triggered": KindSpec(
        severity="WARN",
        message_template="Popup triggered",
        importance="HIGH",
    ),
    "note.created": KindSpec(
        severity="INFO",
        message_template="Note created",
        importance="NORMAL",
    ),
    "review.opened": KindSpec(
        severity="INFO",
        message_template="Review opened: {title}",
        importance="NORMAL",
    ),
}


def spec_for_purity_kind(kind: str) -> Optional[KindSpec]:
    """Return the KindSpec for *kind*, or ``_DEFAULT_KIND_SPEC`` if not found."""
    return PURITY_KIND_MAP.get(kind, _DEFAULT_KIND_SPEC)


def classify_purity_row_type(row: LogRow) -> int:
    """Map a purity log row to a single viewer type bit."""
    kind = str(row.kind or "")
    if kind.startswith("system."):
        return TYPE_SYSTEM
    if kind.startswith("chrome."):
        return TYPE_WEB
    if kind.startswith("popup."):
        return TYPE_INTERVENTION
    if kind.startswith("note."):
        return TYPE_NOTES
    if kind.startswith("review."):
        return TYPE_REVIEW
    return TYPE_MISC
