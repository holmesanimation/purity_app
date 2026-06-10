from PySide6.QtWidgets import QApplication, QDialog

from purity_app.ui.intervention.web_popup import (
    WebPopup,
    _WEB_VERSES,
    _evaluate_verse,
    _is_proper_sentence,
)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# _evaluate_verse
# ---------------------------------------------------------------------------

def test_evaluate_verse_exact_match() -> None:
    accuracy, missing, misspelled, bad = _evaluate_verse(
        "God is faithful", "God is faithful"
    )
    assert accuracy == 100
    assert missing == 0
    assert misspelled == 0
    assert bad == []


def test_evaluate_verse_completely_empty_typed() -> None:
    accuracy, missing, misspelled, _ = _evaluate_verse("", "God is faithful")
    assert accuracy == 0
    assert missing == 3


def test_evaluate_verse_misspelled_word() -> None:
    # "faithfull" is close enough to "faithful" (ratio > 0.6)
    accuracy, missing, misspelled, bad = _evaluate_verse(
        "God is faithfull", "God is faithful"
    )
    assert misspelled == 1
    assert missing == 0
    assert len(bad) == 1


def test_evaluate_verse_missing_word() -> None:
    # "xyz" is not close to "faithful"
    accuracy, missing, misspelled, bad = _evaluate_verse(
        "God is xyz", "God is faithful"
    )
    assert missing == 1
    assert misspelled == 0


# ---------------------------------------------------------------------------
# _is_proper_sentence
# ---------------------------------------------------------------------------

def test_is_proper_sentence_valid() -> None:
    assert _is_proper_sentence("I am going online to check my work email.") is True


def test_is_proper_sentence_four_words() -> None:
    assert _is_proper_sentence("work stuff and things") is True


def test_is_proper_sentence_too_short() -> None:
    assert _is_proper_sentence("Work stuff") is False
    assert _is_proper_sentence("three words only") is False


def test_is_proper_sentence_no_capital_still_valid() -> None:
    # capital no longer required — 4 words suffice
    assert _is_proper_sentence("going online for research") is True


def test_is_proper_sentence_empty() -> None:
    assert _is_proper_sentence("") is False
    assert _is_proper_sentence("   ") is False


# ---------------------------------------------------------------------------
# WebPopup — widget smoke tests
# ---------------------------------------------------------------------------

def test_web_popup_permitted_commit_btn_disabled_initially() -> None:
    _app()
    popup = WebPopup(permitted=True)
    assert popup._commit_btn.isEnabled() is False


def test_web_popup_permitted_commit_btn_enabled_for_valid_purpose() -> None:
    _app()
    popup = WebPopup(permitted=True)
    popup._reason_edit.setPlainText("I am going online to check my work email.")
    assert popup._commit_btn.isEnabled() is True


def test_web_popup_permitted_feelings_grid_hidden_until_revealed() -> None:
    _app()
    popup = WebPopup(permitted=True)
    assert popup._feelings_widget.isHidden() is True
    popup._reveal_feelings()
    assert popup._feelings_widget.isHidden() is False


def test_web_popup_permitted_commit_sets_result_fields() -> None:
    _app()
    popup = WebPopup(permitted=True)
    popup._reason_edit.setPlainText("I am going online to check my work email.")
    popup._reveal_feelings()
    popup._toggle_feeling("anxious", "Anxious", popup._feeling_btns["anxious"])
    popup._toggle_feeling("determined", "Determined", popup._feeling_btns["determined"])
    popup._time_combo.setCurrentIndex(2)

    popup._on_commit()

    assert popup.result() == QDialog.DialogCode.Accepted
    assert popup.selected_choice == "internet_session"
    assert popup.reason_text == "I am going online to check my work email."
    assert popup.allowed_urls == []
    assert popup.duration_seconds == 15 * 60
    assert popup.selected_feelings == ["anxious", "determined"]


def test_web_popup_permitted_uses_default_verse_when_no_reason_id() -> None:
    _app()
    popup = WebPopup(permitted=True)
    # verse is randomized from _WEB_VERSES — verify it resolves to a known entry
    assert popup._verse_ref in {v[1] for v in _WEB_VERSES.values()}


def test_web_popup_permitted_uses_verse_for_known_reason_id() -> None:
    _app()
    popup = WebPopup(permitted=True, reason_id="lonely")
    assert "Psalm" in popup._verse_ref


def test_web_popup_permitted_falls_back_for_unknown_reason_id() -> None:
    _app()
    popup = WebPopup(permitted=True, reason_id="nonexistent_key")
    # unknown key → random pick from known verses
    assert popup._verse_ref in {v[1] for v in _WEB_VERSES.values()}


def test_web_popup_blocked_shows_dismiss() -> None:
    _app()
    popup = WebPopup(permitted=False)
    assert popup.height() == WebPopup.DEFAULT_HEIGHT_BLOCKED
