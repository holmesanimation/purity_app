"""Panic intervention session — state machine, model, and outcome tracking."""

from __future__ import annotations

import uuid
from enum import Enum, auto
from typing import Optional


class PanicSessionState(Enum):
    INTERRUPTING = auto()
    SELECTING_REASONS = auto()
    REFLECTION = auto()
    REORIENTATION = auto()
    COUNTDOWN = auto()
    POST_RECOVERY = auto()
    CLOSED = auto()


class PanicSessionOutcome(Enum):
    RECOVERED = "recovered"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"
    INTERRUPTED = "interrupted"


_LEGAL_TRANSITIONS: dict[PanicSessionState, set[PanicSessionState]] = {
    PanicSessionState.INTERRUPTING: {PanicSessionState.SELECTING_REASONS},
    PanicSessionState.SELECTING_REASONS: {
        PanicSessionState.REFLECTION,
        PanicSessionState.REORIENTATION,
    },
    PanicSessionState.REFLECTION: {PanicSessionState.REORIENTATION},
    PanicSessionState.REORIENTATION: {
        PanicSessionState.COUNTDOWN,
        PanicSessionState.REFLECTION,
    },
    PanicSessionState.COUNTDOWN: {PanicSessionState.POST_RECOVERY},
    PanicSessionState.POST_RECOVERY: {PanicSessionState.CLOSED},
    PanicSessionState.CLOSED: set(),
}


class PanicSession:
    """
    Formal state machine for a single panic intervention session.

    Guarded transition methods raise ``ValueError`` when called from an illegal
    state. This prevents double-countdowns, stale acknowledgements, and
    mutations after close.
    """

    def __init__(self) -> None:
        self.panic_session_id: str = str(uuid.uuid4())
        self.selected_reason_ids: list[str] = []
        self.reflections: dict[str, str] = {}
        self.reoriented_reason_ids: set[str] = set()
        self.countdown_started: bool = False
        self.notify_stub_clicked: bool = False
        self.started_while_elevated: bool = False
        self.state: PanicSessionState = PanicSessionState.INTERRUPTING
        self.outcome: Optional[PanicSessionOutcome] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_state(self, *allowed: PanicSessionState) -> None:
        if self.state not in allowed:
            allowed_names = ", ".join(s.name for s in allowed)
            raise ValueError(
                f"Cannot transition from {self.state.name}; "
                f"allowed source states: {allowed_names}"
            )

    def _transition(self, target: PanicSessionState) -> None:
        legal = _LEGAL_TRANSITIONS.get(self.state, set())
        if target not in legal:
            raise ValueError(
                f"Illegal transition {self.state.name} → {target.name}"
            )
        self.state = target

    # ------------------------------------------------------------------
    # Public transition methods
    # ------------------------------------------------------------------

    def start_interrupting(self) -> None:
        """Re-assert INTERRUPTING — only valid if already in that state."""
        self._require_state(PanicSessionState.INTERRUPTING)

    def start_reason_selection(self) -> None:
        self._transition(PanicSessionState.SELECTING_REASONS)

    def start_reflection(self) -> None:
        self._transition(PanicSessionState.REFLECTION)

    def start_reorientation(self) -> None:
        self._transition(PanicSessionState.REORIENTATION)

    def reorient_topic(self, reason_id: str, reflection_text: str = "") -> None:
        """
        Record that the user has acknowledged *reason_id*.

        Valid from REFLECTION or REORIENTATION states.
        Raises ``ValueError`` if the session is CLOSED.
        """
        self._require_state(
            PanicSessionState.REFLECTION,
            PanicSessionState.REORIENTATION,
        )
        if self.state == PanicSessionState.CLOSED:
            raise ValueError("Cannot reorient a closed session.")
        if reflection_text:
            self.reflections[reason_id] = reflection_text
        self.reoriented_reason_ids.add(reason_id)

    def start_countdown(self) -> None:
        """
        Transition to COUNTDOWN.  Raises ``ValueError`` if countdown has
        already started or not all selected reasons are reoriented.
        """
        if self.countdown_started:
            raise ValueError("Countdown has already started for this session.")
        self._transition(PanicSessionState.COUNTDOWN)
        self.countdown_started = True

    def complete_countdown(self) -> None:
        self._transition(PanicSessionState.POST_RECOVERY)

    def close(self, outcome: PanicSessionOutcome) -> None:
        """
        Close the session with *outcome*.

        Can be called from any non-CLOSED state for forced-close / abandonment
        scenarios, as well as the normal POST_RECOVERY → CLOSED path.
        """
        if self.state == PanicSessionState.CLOSED:
            raise ValueError("Session is already closed.")
        self.outcome = outcome
        self.state = PanicSessionState.CLOSED
