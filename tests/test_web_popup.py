from PySide6.QtWidgets import QApplication

from purity_app.ui.intervention.web_popup import (
    WebSessionConfigPopup,
    is_permitted_web_choice,
)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_tempted_is_not_a_permitted_web_choice() -> None:
    assert is_permitted_web_choice("Tempted") is False


def test_work_is_a_permitted_web_choice() -> None:
    assert is_permitted_web_choice("Work") is True


def test_session_popup_ok_requires_non_whitespace_text() -> None:
    app = _app()
    popup = WebSessionConfigPopup(choice_label="Work")

    assert popup._ok_btn.isEnabled() is False

    popup._urls_edit.setPlainText("   ")
    app.processEvents()
    assert popup._ok_btn.isEnabled() is False

    popup._urls_edit.setPlainText("https://example.com")
    app.processEvents()
    assert popup._ok_btn.isEnabled() is True


def test_session_popup_parses_urls_and_selected_duration() -> None:
    popup = WebSessionConfigPopup(choice_label="Work")

    popup._urls_edit.setPlainText("https://example.com\nhttps://docs.python.org/3/")
    popup._time_combo.setCurrentIndex(2)
    popup._on_commit()

    assert popup.allowed_urls == ["https://example.com", "https://docs.python.org/3/"]
    assert popup.duration_seconds == 15 * 60


def test_session_popup_rejects_invalid_urls() -> None:
    popup = WebSessionConfigPopup(choice_label="Research")

    popup._urls_edit.setPlainText("not-a-url")
    popup._on_commit()

    assert popup.allowed_urls == []
    assert popup._validation_lbl.isHidden() is False
    assert "Invalid URL" in popup._validation_lbl.text()