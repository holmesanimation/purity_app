"""Smoke tests for the WebTimerPill widget."""

from PySide6.QtWidgets import QApplication

from purity_app.ui.web_timer_pill import WebTimerPill


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_import_and_instantiate() -> None:
    """WebTimerPill can be imported and constructed without a parent."""
    _app()
    pill = WebTimerPill(timeout_seconds=300)
    assert pill is not None
    pill.hide()


def test_default_label_format() -> None:
    """Initial label shows 'Web 05:00' for a 300-second timeout."""
    _app()
    pill = WebTimerPill(timeout_seconds=300)
    # Force a label refresh at the initial remaining time
    pill._update_label()
    assert pill._label.text() == "Web 05:00"


def test_set_timeout_takes_effect_on_start() -> None:
    """set_timeout changes the countdown duration used on the next start."""
    _app()
    pill = WebTimerPill(timeout_seconds=300)
    pill.set_timeout(60)
    pill.start_session()
    pill._tick_timer.stop()  # don't let it actually run
    assert pill._remaining == 60
    pill.stop_session()


def test_stop_session_hides_pill() -> None:
    _app()
    pill = WebTimerPill(timeout_seconds=10)
    pill.start_session()
    assert pill.isVisible()
    pill.stop_session()
    assert not pill.isVisible()


def test_session_expired_signal_fires_at_zero() -> None:
    _app()
    pill = WebTimerPill(timeout_seconds=1)
    fired: list[bool] = []
    pill.session_expired.connect(lambda: fired.append(True))
    pill.start_session()
    pill._tick_timer.stop()
    pill._remaining = 1
    pill._tick()  # drives remaining to 0 and emits
    assert fired == [True]
    pill.stop_session()


def test_start_extension_warning_pauses_main_timer() -> None:
    """start_extension_warning pauses the session tick and activates flash."""
    _app()
    pill = WebTimerPill(timeout_seconds=300)
    pill.start_session()
    assert pill._tick_timer.isActive()
    assert not pill.is_warning_active

    pill.start_extension_warning(30)

    assert pill.is_warning_active is True
    assert not pill._tick_timer.isActive()
    assert pill._warning_flash_timer.isActive()
    pill.stop_session()


def test_clear_extension_warning_resumes_main_timer() -> None:
    """clear_extension_warning cancels warning and resumes the countdown."""
    _app()
    pill = WebTimerPill(timeout_seconds=300)
    pill.start_session()
    pill.start_extension_warning(30)
    pill.clear_extension_warning()

    assert pill.is_warning_active is False
    assert pill._tick_timer.isActive()
    assert not pill._warning_flash_timer.isActive()
    assert not pill._warning_countdown_timer.isActive()
    pill.stop_session()


def test_extension_warning_expired_signal_fires_at_zero() -> None:
    """extension_warning_expired emits when the 30-second countdown hits zero."""
    _app()
    pill = WebTimerPill(timeout_seconds=300)
    fired: list[bool] = []
    pill.extension_warning_expired.connect(lambda: fired.append(True))
    pill.start_session()
    pill.start_extension_warning(1)

    # Skip flash phase and enter countdown immediately
    pill._warning_flash_timer.stop()
    pill._warning_flash_count = pill._warning_flash_max
    pill._warning_remaining = 1
    pill._warning_countdown_timer.start()
    pill._warning_countdown_tick()  # drives remaining to 0, emits signal

    assert fired == [True]
    assert pill.is_warning_active is False
    pill.stop_session()


def test_stop_session_cancels_warning_state() -> None:
    """stop_session clears all warning timers so no dangling callbacks remain."""
    _app()
    pill = WebTimerPill(timeout_seconds=300)
    pill.start_session()
    pill.start_extension_warning(30)
    pill.stop_session()

    assert not pill.isVisible()
    assert pill.is_warning_active is False
    assert not pill._warning_flash_timer.isActive()
    assert not pill._warning_countdown_timer.isActive()
