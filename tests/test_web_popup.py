from PySide6.QtWidgets import QApplication

from purity_app.ui.intervention.web_popup import (
    WebReasonPopup,
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


def test_reason_popup_commit_requires_non_whitespace_text() -> None:
    app = _app()
    popup = WebReasonPopup(choice_label="Work")

    assert popup._commit_btn.isEnabled() is False

    popup._reason_edit.setPlainText("   ")
    app.processEvents()
    assert popup._commit_btn.isEnabled() is False

    popup._reason_edit.setPlainText("Need to read one article.")
    app.processEvents()
    assert popup._commit_btn.isEnabled() is True