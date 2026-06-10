from __future__ import annotations

import os
import time
from typing import Callable

from shane_common.notify.adapters.base import INotifyAdapter
from shane_common.notify.builder import build_telegram_adapter
from shane_common.notify.contracts import NotificationEvent, NotificationSeverity
from shane_common.preferences.manager import SettingsManager

_TELEGRAM_CATEGORY = "app.telegram"


def build_telegram_adapter_from_settings(
    settings_manager: SettingsManager,
    *,
    format_message: Callable[[NotificationEvent], str] | None = None,
) -> INotifyAdapter:
    token = os.environ.get("PURITY_TELEGRAM_TOKEN", "").strip()
    chat_ids_str = str(settings_manager.get(_TELEGRAM_CATEGORY, "telegram_chat_ids") or "")
    chat_ids = [
        int(chunk.strip())
        for chunk in chat_ids_str.split(",")
        if chunk.strip()
    ]
    return build_telegram_adapter(
        token,
        chat_ids,
        frozenset({"WARNING", "URGENT"}),
        format_message=format_message,
    )


def make_lifecycle_event(kind: str, details: str | None = None) -> NotificationEvent:
    return NotificationEvent(
        ts=time.time(),
        severity=NotificationSeverity.WARNING,
        kind=kind,
        scope="global",
        details=details,
    )
