from __future__ import annotations

import time

from shane_common.notify.contracts import NotificationEvent, NotificationSeverity

from services.pulse_models import PulseSliders


REACH_OUT_TITLE = "Reach Out to the group"
REACH_OUT_VERSE = (
    '"Bear one another\'s burdens, and so fulfill the law of Christ." '
    "- Galatians 6:2"
)


def format_notification_details(event: NotificationEvent) -> str:
    return str(event.details or "")


def render_pulse_reach_out_details(sliders: PulseSliders, user_message: str) -> str:
    lines = ["Pulse:"]
    for label, value in sliders.negative_items():
        lines.append(f"{label}: {value}")

    lines.append("")
    lines.append("Shane submitted a pulse check and may need encouragement.")
    lines.append("")
    lines.append(user_message.strip())
    return "\n".join(lines).strip()


def make_pulse_reach_out_event(
    *,
    sliders: PulseSliders,
    user_message: str,
) -> NotificationEvent:
    return NotificationEvent(
        ts=time.time(),
        severity=NotificationSeverity.WARNING,
        kind="pulse.reach_out",
        scope="global",
        details=render_pulse_reach_out_details(sliders, user_message),
    )


def make_hard_block_alert_event() -> NotificationEvent:
    return NotificationEvent(
        ts=time.time(),
        severity=NotificationSeverity.WARNING,
        kind="browser.hard_block",
        scope="global",
        details="Shane has typed one of his hard blocked sexual phrases into his browser",
    )


def make_web_session_reach_out_event(*, reason: str) -> NotificationEvent:
    lines = [
        "Shane closed a browser session and indicated he did not honor Jesus online.",
        "",
        f'Session reason: "{reason.strip()}"' if reason.strip() else "No session reason recorded.",
        "",
        "He may need encouragement or accountability from the group.",
    ]
    return NotificationEvent(
        ts=time.time(),
        severity=NotificationSeverity.WARNING,
        kind="web_session.reach_out",
        scope="global",
        details="\n".join(lines).strip(),
    )