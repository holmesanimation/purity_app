"""Tests for PanicSession state machine."""

from __future__ import annotations

import pytest

from purity_app.services.panic_session import (
    PanicSession,
    PanicSessionOutcome,
    PanicSessionState,
)


class TestPanicSessionTransitions:
    def test_initial_state_is_interrupting(self) -> None:
        s = PanicSession()
        assert s.state == PanicSessionState.INTERRUPTING

    def test_session_id_is_uuid_string(self) -> None:
        s = PanicSession()
        assert isinstance(s.panic_session_id, str)
        assert len(s.panic_session_id) == 36  # standard UUID4

    def test_two_sessions_have_different_ids(self) -> None:
        assert PanicSession().panic_session_id != PanicSession().panic_session_id

    def test_start_reason_selection(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        assert s.state == PanicSessionState.SELECTING_REASONS

    def test_start_reflection(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        s.start_reflection()
        assert s.state == PanicSessionState.REFLECTION

    def test_start_reorientation_from_reflection(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        s.start_reflection()
        s.start_reorientation()
        assert s.state == PanicSessionState.REORIENTATION

    def test_start_reorientation_from_selecting_reasons(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        s.start_reorientation()
        assert s.state == PanicSessionState.REORIENTATION

    def test_start_countdown(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        s.start_reorientation()
        s.start_countdown()
        assert s.state == PanicSessionState.COUNTDOWN
        assert s.countdown_started is True

    def test_complete_countdown(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        s.start_reorientation()
        s.start_countdown()
        s.complete_countdown()
        assert s.state == PanicSessionState.POST_RECOVERY

    def test_close_from_post_recovery(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        s.start_reorientation()
        s.start_countdown()
        s.complete_countdown()
        s.close(PanicSessionOutcome.RECOVERED)
        assert s.state == PanicSessionState.CLOSED
        assert s.outcome == PanicSessionOutcome.RECOVERED

    def test_close_from_any_non_closed_state(self) -> None:
        """Force-close mid-session (ABANDONED outcome) must work from any state."""
        s = PanicSession()
        s.start_reason_selection()
        s.close(PanicSessionOutcome.ABANDONED)
        assert s.state == PanicSessionState.CLOSED
        assert s.outcome == PanicSessionOutcome.ABANDONED

    def test_close_when_already_closed_raises(self) -> None:
        s = PanicSession()
        s.close(PanicSessionOutcome.ABANDONED)
        with pytest.raises(ValueError):
            s.close(PanicSessionOutcome.RECOVERED)

    def test_duplicate_countdown_raises(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        s.start_reorientation()
        s.start_countdown()
        with pytest.raises(ValueError):
            s.start_countdown()

    def test_illegal_transition_raises(self) -> None:
        s = PanicSession()
        # Cannot jump from INTERRUPTING straight to COUNTDOWN
        with pytest.raises(ValueError):
            s.start_countdown()

    def test_reason_selection_to_countdown_invalid(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        with pytest.raises(ValueError):
            s.start_countdown()

    def test_reorient_topic_records_reflection(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        s.start_reorientation()
        s.reorient_topic("lonely", "Feeling isolated right now.")
        assert "lonely" in s.reoriented_reason_ids
        assert s.reflections["lonely"] == "Feeling isolated right now."

    def test_reorient_topic_without_text(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        s.start_reorientation()
        s.reorient_topic("tired")
        assert "tired" in s.reoriented_reason_ids
        assert "tired" not in s.reflections

    def test_reorient_topic_from_closed_raises(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        s.start_reorientation()
        s.close(PanicSessionOutcome.ABANDONED)
        with pytest.raises(ValueError):
            s.reorient_topic("tired")

    def test_started_while_elevated_defaults_false(self) -> None:
        s = PanicSession()
        assert s.started_while_elevated is False

    def test_started_while_elevated_can_be_set(self) -> None:
        s = PanicSession()
        s.started_while_elevated = True
        assert s.started_while_elevated is True

    def test_outcome_none_until_closed(self) -> None:
        s = PanicSession()
        s.start_reason_selection()
        assert s.outcome is None

    def test_all_outcomes_settable(self) -> None:
        for outcome in PanicSessionOutcome:
            s = PanicSession()
            s.close(outcome)
            assert s.outcome == outcome
