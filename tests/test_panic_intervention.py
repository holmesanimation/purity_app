"""Tests for MainWindow._start_panic_intervention() (Chat 3)."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from purity_app.services.browser_session import BrowserSessionManager
from services.panic_session import PanicSessionState
from purity_app.services.runtime import PurityRuntime, create_purity_runtime


def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


_TASKKILL_PATCH = "shane_common.processes.windows.taskkill_processes"
_REASON_DIALOG_PATCH = "ui.intervention.panic_reason_dialog.PanicReasonDialog"
_INTERVENTION_WINDOW_PATCH = "ui.intervention.panic_intervention_window.PanicInterventionWindow"


@contextmanager
def _patched_panic_dialogs(reason_ids=None):
    """Patch both panic UI dialogs to accept without display interaction."""
    from PySide6.QtWidgets import QDialog
    if reason_ids is None:
        reason_ids = ["lonely"]
    fake_dialog = MagicMock()
    fake_dialog.exec.return_value = QDialog.DialogCode.Accepted
    fake_dialog.selected_reason_ids = reason_ids
    fake_window = MagicMock()
    fake_window.isVisible.return_value = False
    with (
        patch(_REASON_DIALOG_PATCH, return_value=fake_dialog),
        patch(_INTERVENTION_WINDOW_PATCH, return_value=fake_window),
    ):
        yield fake_dialog, fake_window


def _all_jsonl_lines(root: Path) -> list[dict]:
    lines: list[dict] = []
    for f in root.rglob("*.jsonl"):
        for raw in f.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if raw:
                lines.append(json.loads(raw))
    return lines


def _lines_for_kind(root: Path, kind: str) -> list[dict]:
    return [l for l in _all_jsonl_lines(root) if l.get("kind") == kind]


# ---------------------------------------------------------------------------
# Helpers to build a minimal MainWindow under test
# ---------------------------------------------------------------------------

def _make_main_window(tmp_path: Path, runtime: PurityRuntime | None):
    """Return a MainWindow instance with heavy subsystems monkeypatched."""
    import app as app_module

    # Stub WebWatcherService so it doesn't spin up OS-level watchers.
    fake_watcher = MagicMock()
    fake_watcher.web_opened = MagicMock()
    fake_watcher.web_opened.connect = MagicMock()
    fake_watcher.start = MagicMock()

    # Stub PanicButton (no display needed).
    fake_panic_btn = MagicMock()
    fake_panic_btn.panic_requested = MagicMock()
    fake_panic_btn.panic_requested.connect = MagicMock()

    with (
        patch("app.WebWatcherService", return_value=fake_watcher),
        patch("app.PanicButton", return_value=fake_panic_btn),
    ):
        mgr = BrowserSessionManager(tmp_path)
        win = app_module.MainWindow(
            runtime=runtime,
            browser_session_manager=mgr,
        )

    win._panic_btn = fake_panic_btn
    return win


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStartPanicIntervention:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        _qapp()
        self.tmp_path = tmp_path
        self.runtime = create_purity_runtime(tmp_path)
        self.win = _make_main_window(tmp_path, self.runtime)

    def _run_intervention(self) -> None:
        with patch(_TASKKILL_PATCH) as mock_kill:
            self.win._start_panic_intervention()
            self.mock_kill = mock_kill

    def test_session_created_in_selecting_reasons_state(self) -> None:
        with patch(_TASKKILL_PATCH), _patched_panic_dialogs():
            self.win._start_panic_intervention()

        assert self.win._active_panic_session is not None
        assert self.win._active_panic_session.state == PanicSessionState.SELECTING_REASONS

    def test_browsers_killed(self) -> None:
        with patch(_TASKKILL_PATCH) as mock_kill:
            self.win._start_panic_intervention()

        mock_kill.assert_called_once()

    def test_timer_pill_stopped(self) -> None:
        with patch(_TASKKILL_PATCH):
            self.win._start_panic_intervention()

        # pill should not be visible (stop_session hides it)
        assert not self.win._web_timer_pill.isVisible()

    def test_browser_session_cleared(self) -> None:
        self.win._browser_session_manager.start_session(
            purpose="Work",
            allowed_urls=["https://example.com"],
            duration_seconds=300,
        )
        with patch(_TASKKILL_PATCH):
            self.win._start_panic_intervention()

        payload = self.win._browser_session_manager.get_session_payload()
        assert not payload.get("is_active", False)

    def test_panic_started_event_emitted(self) -> None:
        with patch(_TASKKILL_PATCH):
            self.win._start_panic_intervention()

        self.runtime.journal.close_sinks()
        events = _lines_for_kind(self.tmp_path, "panic.started")
        assert events, "panic.started event not found"
        payload = events[0]["payload"]
        assert payload["panic_session_id"] == self.win._active_panic_session.panic_session_id

    def test_started_while_elevated_captured(self) -> None:
        self.win._panic_elevated = True
        with patch(_TASKKILL_PATCH):
            self.win._start_panic_intervention()

        assert self.win._active_panic_session.started_while_elevated is True
        self.runtime.journal.close_sinks()
        events = _lines_for_kind(self.tmp_path, "panic.started")
        assert events[0]["payload"]["started_while_elevated"] is True

    def test_web_session_fields_cleared(self) -> None:
        self.win._web_session_reason = "some reason"
        self.win._web_session_choice = "Work"
        self.win._web_session_urls = ["https://example.com"]
        self.win._web_session_duration_seconds = 300

        with patch(_TASKKILL_PATCH):
            self.win._start_panic_intervention()

        assert self.win._web_session_reason == ""
        assert self.win._web_session_choice == ""
        assert self.win._web_session_urls == []
        assert self.win._web_session_duration_seconds is None


class TestStartPanicInterventionDuplicate:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        _qapp()
        self.tmp_path = tmp_path
        self.runtime = create_purity_runtime(tmp_path)
        self.win = _make_main_window(tmp_path, self.runtime)

    def test_duplicate_call_raises_existing_window_not_new_session(self) -> None:
        fake_window = MagicMock()
        fake_window.isVisible.return_value = True

        with patch(_TASKKILL_PATCH), _patched_panic_dialogs():
            self.win._start_panic_intervention()

        first_session = self.win._active_panic_session
        self.win._active_panic_window = fake_window

        # Second call — session window visible → short-circuits before kill
        with patch(_TASKKILL_PATCH) as mock_kill2:
            self.win._start_panic_intervention()

        # No second kill, same session object
        mock_kill2.assert_not_called()
        assert self.win._active_panic_session is first_session
        fake_window.raise_.assert_called_once()
        fake_window.activateWindow.assert_called_once()

    def test_second_call_creates_new_session_when_window_not_visible(self) -> None:
        fake_window = MagicMock()
        fake_window.isVisible.return_value = False

        with patch(_TASKKILL_PATCH), _patched_panic_dialogs():
            self.win._start_panic_intervention()

        first_session = self.win._active_panic_session
        self.win._active_panic_window = fake_window

        with patch(_TASKKILL_PATCH), _patched_panic_dialogs():
            self.win._start_panic_intervention()

        # A new session is created when the old window is no longer visible
        assert self.win._active_panic_session is not first_session


# ---------------------------------------------------------------------------
# PanicReasonDialog tests (Chat 4)
# ---------------------------------------------------------------------------

class TestPanicReasonDialog:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        _qapp()

    def _make_dialog(self, stats=None):
        from ui.intervention.panic_reason_dialog import PanicReasonDialog
        return PanicReasonDialog(stats=stats)

    def test_help_me_disabled_initially(self) -> None:
        dlg = self._make_dialog()
        assert not dlg._help_btn.isEnabled()

    def test_help_me_enabled_after_selection(self) -> None:
        dlg = self._make_dialog()
        # Check the first reason
        first_cb = list(dlg._checkboxes.values())[0]
        first_cb.setChecked(True)
        assert dlg._help_btn.isEnabled()

    def test_help_me_disabled_again_when_deselected(self) -> None:
        dlg = self._make_dialog()
        first_cb = list(dlg._checkboxes.values())[0]
        first_cb.setChecked(True)
        first_cb.setChecked(False)
        assert not dlg._help_btn.isEnabled()

    def test_selected_reason_ids_populated_on_accept(self) -> None:
        from ui.intervention.panic_reason_dialog import PanicReasonDialog, REASON_LABELS
        dlg = self._make_dialog()
        expected_id = REASON_LABELS[2][0]  # "tired"
        dlg._checkboxes[expected_id].setChecked(True)
        dlg._on_accept()
        assert dlg.selected_reason_ids == [expected_id]

    def test_multiple_selected_reason_ids(self) -> None:
        from ui.intervention.panic_reason_dialog import REASON_LABELS
        dlg = self._make_dialog()
        ids_to_select = [REASON_LABELS[0][0], REASON_LABELS[3][0]]
        for rid in ids_to_select:
            dlg._checkboxes[rid].setChecked(True)
        dlg._on_accept()
        assert set(dlg.selected_reason_ids) == set(ids_to_select)

    def test_awareness_copy_shown_when_stats_have_recurring_reasons(self) -> None:
        from unittest.mock import MagicMock
        from ui.intervention.panic_reason_dialog import REASON_LABELS
        stats = MagicMock()
        # Return top 2 recurring reasons that are in the displayed list
        stats.get_top_reasons.return_value = [REASON_LABELS[0][0], REASON_LABELS[1][0]]
        dlg = self._make_dialog(stats=stats)
        assert not dlg._awareness_label.isHidden()

    def test_awareness_copy_hidden_when_only_one_recurring_reason(self) -> None:
        from unittest.mock import MagicMock
        from ui.intervention.panic_reason_dialog import REASON_LABELS
        stats = MagicMock()
        stats.get_top_reasons.return_value = [REASON_LABELS[0][0]]
        dlg = self._make_dialog(stats=stats)
        assert not dlg._awareness_label.isVisible()

    def test_awareness_copy_never_contains_numeric_counts(self) -> None:
        from unittest.mock import MagicMock
        from ui.intervention.panic_reason_dialog import REASON_LABELS
        import re
        stats = MagicMock()
        stats.get_top_reasons.return_value = [REASON_LABELS[0][0], REASON_LABELS[1][0]]
        dlg = self._make_dialog(stats=stats)
        text = dlg._awareness_label.text()
        # No bare digits (counts) should appear in the copy
        assert not re.search(r"\b\d+\b", text), f"Numeric count found in awareness copy: {text!r}"

    def test_awareness_copy_hidden_when_no_stats(self) -> None:
        dlg = self._make_dialog(stats=None)
        assert not dlg._awareness_label.isVisible()


# ---------------------------------------------------------------------------
# PanicInterventionWindow tests (Chat 4)
# ---------------------------------------------------------------------------

def _make_session_with_reasons(reason_ids: list[str]):
    """Return a PanicSession ready for REORIENTATION with the given reasons."""
    from services.panic_session import PanicSession
    session = PanicSession()
    session.selected_reason_ids = reason_ids
    session.start_reason_selection()
    return session


class TestPanicInterventionWindow:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        _qapp()

    def _make_window(self, reason_ids=None, runtime=None):
        from ui.intervention.panic_intervention_window import PanicInterventionWindow
        if reason_ids is None:
            reason_ids = ["lonely", "tired"]
        session = _make_session_with_reasons(reason_ids)
        return PanicInterventionWindow(session=session, runtime=runtime), session

    def test_progress_label_starts_at_zero(self) -> None:
        win, session = self._make_window(["lonely", "tired"])
        assert win._progress_label.text() == "0 / 2 topics"

    def test_progress_label_updates_on_praise(self) -> None:
        win, session = self._make_window(["lonely", "tired"])
        win._on_praise("lonely")
        assert win._progress_label.text() == "1 / 2 topics"

    def test_countdown_not_started_before_all_topics_reoriented(self) -> None:
        win, session = self._make_window(["lonely", "tired"])
        win._on_praise("lonely")
        # countdown container should still be hidden
        assert not win._countdown_container.isVisible()
        assert not session.countdown_started

    def test_countdown_starts_after_all_topics_reoriented(self) -> None:
        win, session = self._make_window(["lonely"])
        win._on_praise("lonely")
        assert not win._countdown_container.isHidden()
        assert session.countdown_started

    def test_close_session_button_hidden_until_countdown_completes(self) -> None:
        win, session = self._make_window(["lonely"])
        win._on_praise("lonely")
        # Countdown running — close button not yet visible
        assert not win._close_session_btn.isVisible()

    def test_close_session_button_shown_after_countdown(self) -> None:
        win, session = self._make_window(["lonely"])
        win._on_praise("lonely")
        win._finish_countdown()
        assert not win._close_session_btn.isHidden()

    def test_session_outcome_recovered_on_close_session(self) -> None:
        from services.panic_session import PanicSessionOutcome, PanicSessionState
        win, session = self._make_window(["lonely"])
        win._on_praise("lonely")
        win._finish_countdown()
        win._on_close_session()
        assert session.outcome == PanicSessionOutcome.RECOVERED
        assert session.state == PanicSessionState.CLOSED

    def test_session_abandoned_on_force_close(self) -> None:
        from services.panic_session import PanicSessionOutcome, PanicSessionState
        from PySide6.QtGui import QCloseEvent
        win, session = self._make_window(["lonely"])
        # Do NOT complete countdown — simulate X-button close
        event = QCloseEvent()
        win.closeEvent(event)
        assert session.outcome == PanicSessionOutcome.ABANDONED
        assert session.state == PanicSessionState.CLOSED

    def test_praise_locks_card(self) -> None:
        win, session = self._make_window(["tired"])
        win._on_praise("tired")
        assert win._reflection_fields["tired"].isReadOnly()
        assert not win._praise_buttons["tired"].isEnabled()

    def test_reflection_text_saved_to_session(self) -> None:
        win, session = self._make_window(["tired"])
        win._reflection_fields["tired"].setPlainText("I need rest.")
        win._on_praise("tired")
        assert session.reflections.get("tired") == "I need rest."

    def test_empty_reflection_not_saved_to_session(self) -> None:
        win, session = self._make_window(["tired"])
        win._reflection_fields["tired"].setPlainText("")
        win._on_praise("tired")
        assert "tired" not in session.reflections

    def test_panic_closed_event_emitted_with_recovered_outcome(self, tmp_path) -> None:
        import json
        runtime = create_purity_runtime(tmp_path)
        win, session = self._make_window(["lonely"], runtime=runtime)
        win._on_praise("lonely")
        win._finish_countdown()
        win._on_close_session()
        runtime.journal.close_sinks()
        events = _lines_for_kind(tmp_path, "panic.closed")
        assert events, "panic.closed event not found"
        assert events[0]["payload"]["outcome"] == "recovered"

