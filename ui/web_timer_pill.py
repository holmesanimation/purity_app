"""Purity-specific web-session timer pill.

Wraps FloatingStatusPill to display a live "Web 00:00" countdown while the
user is in an allowed browser session.  When time expires the pill emits
`session_expired` so the caller can kill the browsers.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtWidgets import QApplication

from shane_common.ui.floating_status_pill import FloatingStatusPill

_ORG = "purity"
_APP = "PurityMonitor"
_POS_X_KEY = "web_timer_pill_pos_x"
_POS_Y_KEY = "web_timer_pill_pos_y"

_COLOR_ACTIVE = "#1d4ed8"   # blue while time remains
_COLOR_EXPIRING = "#b45309"  # amber when < 60 s remain
_COLOR_EXPIRED = "#991b1b"   # red when time is up


class WebTimerPill(FloatingStatusPill):
    """Floating pill that counts down a web session and emits session_expired."""

    from PySide6.QtCore import Signal
    session_expired = Signal()
    extension_warning_expired = Signal()

    def __init__(self, timeout_seconds: int = 300, parent=None) -> None:
        super().__init__(
            parent=parent,
            width=180,
            height=36,
            initial_text="Web 00:00",
            initial_color=_COLOR_ACTIVE,
            tooltip=(
                "Web session timer\n"
                "Double-click to raise Purity  |  Drag to reposition"
            ),
            toggle_action_text="Open Purity",
            quit_action_text="",
            position_x_key=_POS_X_KEY,
            position_y_key=_POS_Y_KEY,
        )
        self._timeout_seconds = timeout_seconds
        self._remaining: int = timeout_seconds
        self._main_window = None  # set by caller

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)

        # Extension-warning flash / countdown state
        self._warning_active = False
        self._warning_remaining = 0
        self._warning_flash_count = 0
        self._warning_flash_max = 6  # 6 × 300 ms ≈ 1.8 s of flashing before settling

        self._warning_flash_timer = QTimer(self)
        self._warning_flash_timer.setInterval(300)
        self._warning_flash_timer.timeout.connect(self._warning_flash_tick)

        self._warning_countdown_timer = QTimer(self)
        self._warning_countdown_timer.setInterval(1000)
        self._warning_countdown_timer.timeout.connect(self._warning_countdown_tick)

        # Restore saved position
        settings = QSettings(_ORG, _APP)
        self.restore_position(settings)

        # Persist position whenever it changes
        self.position_changed.connect(self._save_position)

        # Double-click raises main window
        self.toggle_requested.connect(self._raise_main_window)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_main_window(self, window) -> None:
        self._main_window = window

    def set_timeout(self, seconds: int) -> None:
        """Update the session timeout (takes effect on next start_session)."""
        self._timeout_seconds = seconds

    def start_session(self) -> None:
        """Start (or restart) a new countdown and make the pill visible."""
        self._remaining = self._timeout_seconds
        self._update_label()
        self.show()
        self._tick_timer.start()

    def stop_session(self) -> None:
        """Hide and stop the countdown without emitting session_expired."""
        self._tick_timer.stop()
        self._warning_flash_timer.stop()
        self._warning_countdown_timer.stop()
        self._warning_active = False
        self.hide()

    # ------------------------------------------------------------------
    # Extension-warning API
    # ------------------------------------------------------------------

    @property
    def is_warning_active(self) -> bool:
        return self._warning_active

    def start_extension_warning(self, warning_seconds: int = 30) -> None:
        """Pause the session countdown, flash the pill, then show a 30-second
        red countdown giving the user time to re-enable the extension."""
        if self._warning_active:
            return
        self._warning_active = True
        self._warning_remaining = warning_seconds
        self._warning_flash_count = 0
        self._tick_timer.stop()
        self._warning_flash_timer.start()

    def clear_extension_warning(self) -> None:
        """Stop the extension warning and resume the normal session countdown."""
        if not self._warning_active:
            return
        self._warning_active = False
        self._warning_flash_timer.stop()
        self._warning_countdown_timer.stop()
        self._update_label()
        self._tick_timer.start()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _warning_flash_tick(self) -> None:
        self._warning_flash_count += 1
        # Alternate between the red warning and the normal countdown label.
        if self._warning_flash_count % 2 == 0:
            self._update_label()
        else:
            self.update_status("Extension off", _COLOR_EXPIRED)
        if self._warning_flash_count >= self._warning_flash_max:
            self._warning_flash_timer.stop()
            mins, secs = divmod(self._warning_remaining, 60)
            self.update_status(f"Re-enable ext: {mins}:{secs:02d}", _COLOR_EXPIRED)
            self._warning_countdown_timer.start()

    def _warning_countdown_tick(self) -> None:
        self._warning_remaining -= 1
        if self._warning_remaining > 0:
            mins, secs = divmod(self._warning_remaining, 60)
            self.update_status(f"Re-enable ext: {mins}:{secs:02d}", _COLOR_EXPIRED)
        else:
            self._warning_countdown_timer.stop()
            self._warning_active = False
            self.extension_warning_expired.emit()

    def _tick(self) -> None:
        self._remaining -= 1
        self._update_label()
        if self._remaining <= 0:
            self._tick_timer.stop()
            self.session_expired.emit()

    def _update_label(self) -> None:
        remaining = max(0, self._remaining)
        mins, secs = divmod(remaining, 60)
        text = f"Web {mins:02d}:{secs:02d}"
        if remaining <= 0:
            color = _COLOR_EXPIRED
        elif remaining <= 60:
            color = _COLOR_EXPIRING
        else:
            color = _COLOR_ACTIVE
        self.update_status(text, color)

    def _save_position(self) -> None:
        settings = QSettings(_ORG, _APP)
        self.save_position(settings)

    def _raise_main_window(self) -> None:
        if self._main_window is not None:
            win = self._main_window
            if win.isMinimized():
                win.showNormal()
            else:
                win.show()
            win.raise_()
            win.activateWindow()
