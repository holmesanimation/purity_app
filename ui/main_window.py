"""Purity application main window.

This module contains ``MainWindow`` and the helper utilities it relies on
(supervisor launcher, startup-log writer, Chrome finder).  Kept separate from
``app.py`` so that the startup/singleton logic there stays small and focused.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from shane_common.preferences.manager import SettingsManager
from shane_common.notes.notes_writer import NoteType
from shane_common.ui.preferences.preferences_dialog import PreferencesDialog
from shane_common.watchdog.heartbeat_reader import HeartbeatReader
from services.browser_session import BrowserSessionManager, ExtensionHeartbeatMonitor
from services.browser_session_watcher import BrowserSessionWatcher
from services.mock_state import MockAppState
from services.notes_setup import make_notes_writer, notes_writer, notes_repo
from services.panic_session import PanicSession, PanicSessionOutcome, PanicSessionState
from services.pulse_activity import UserActivityMonitor
from services.pulse_manager import PulseManager
from services.pulse_models import PulseSliders
from services.pulse_notifications import (
    format_notification_details,
    make_pulse_reach_out_event,
    make_web_session_reach_out_event,
)
from services.streak import PurityStreak
from services.settings_schemas import (
    build_purity_settings_manager,
    get_kill_browsers_on_startup,
    get_permitted_browsers,
    get_prayer_recipients_per_session,
    get_web_session_timeout_seconds,
    resolve_purity_data_root,
)
from services.telegram_notify import build_telegram_adapter_from_settings
from services.web_requests import (
    append_web_request_log,
    mark_app_control_request_done,
    mark_web_launch_request_done,
    read_pending_app_control_requests,
    read_pending_web_launch_requests,
    write_launcher_approved_marker,
)
from services.web_watcher import WebWatcherService
from styles.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_LIGHT,
    COLOR_SURFACE,
    COLOR_BORDER,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_BACKGROUND,
    COLOR_SURFACE_2,
    FONT_FAMILY,
    FONT_SIZE_SMALL,
    FONT_SIZE_NORMAL,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_LARGE,
)
from ui.intervention.panic_button import PanicButton
from ui.intervention.popup_manager import PopupManager
from ui.intervention.web_popup import WebPopup
from ui.left_dock_dashboard import LeftDockDashboard
from ui.notes.note_dialog import NoteDialog
from ui.notes.notes_browser_window import NotesBrowserWindow
from ui.reflection.dashboard import ReflectionDashboard
from ui.review.review_window import ReviewWindow
from ui.system.log_normalizer_sink import PurityLogNormalizerSink
from ui.system.log_viewer_window import PurityLogViewerWindow
from ui.web_timer_pill import WebTimerPill

# ---------------------------------------------------------------------------
# Popup sidebar buttons
# ---------------------------------------------------------------------------
_POPUP_BUTTONS = [
    ("Fire: Web",     "web"),
    ("Fire: Prayer",  "prayer"),
    ("Fire: Risk",    "risk"),
    ("Fire: Hourly",  "hourly"),
    ("Fire: Evening", "evening"),
]

_CHROME_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
]

_EXTENSION_HEARTBEAT_GRACE_SECONDS = 0.0
_UI_TIMER_LAG_THRESHOLD_MS = 50.0

# ---------------------------------------------------------------------------
# Supervisor watchdog constants
# ---------------------------------------------------------------------------
_SUPERVISOR_HEARTBEAT_GRACE_SECONDS = 30.0
_SUPERVISOR_STALE_S = 15.0
_SUPERVISOR_DEAD_S = 10.0

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _append_startup_log(data_root: Path, message: str) -> None:
    """Write a timestamped diagnostic line to startup_debug.log.

    This file is readable even from pythonw.exe instances that have no console.
    Uses ASCII-only content to avoid encoding errors on cp1252 stdout.
    """
    pid = os.getpid()
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"[PurityApp] {ts} [PID={pid}] {message}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        log_path = Path(data_root) / "_system" / "purity" / "startup_debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _find_chrome() -> Path | None:
    for path in _CHROME_PATHS:
        if path.exists():
            return path
    return None


def _launch_supervisor(data_root: Path) -> None:
    """Spawn supervisor.py as a detached child process."""
    import json as _json

    creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

    try:
        subprocess.Popen(
            ["schtasks", "/Run", "/TN", "PuritySupervisor"],
            creationflags=creationflags,
        )
        _append_startup_log(data_root, "Supervisor watchdog launch requested via Scheduled Task.")
        return
    except Exception:
        traceback.print_exc()

    # This module lives at ui/main_window.py — one level below the project root.
    _project_root = Path(__file__).parent.parent
    supervisor_path = _project_root / "supervisor.py"
    if not supervisor_path.exists():
        return
    purity_app_cmd = _json.dumps([sys.executable, str(_project_root / "app.py")])
    cmd = [
        sys.executable,
        str(supervisor_path),
        "--data-root", str(data_root),
        "--purity-app-cmd", purity_app_cmd,
    ]
    try:
        subprocess.Popen(cmd, creationflags=creationflags)
        _append_startup_log(data_root, "Supervisor watchdog launched via direct process spawn.")
    except Exception:
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------


class _BrowserKillWorker(QObject):
    """Runs taskkill_processes off the UI thread (subprocess spawns are slow)."""

    finished = Signal()

    def __init__(self, browsers: list[str]):
        super().__init__()
        self._browsers = browsers

    def run(self) -> None:
        from shane_common.processes.windows import taskkill_processes
        taskkill_processes(self._browsers)
        self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(
        self,
        runtime=None,
        settings_manager: SettingsManager | None = None,
        browser_session_manager: BrowserSessionManager | None = None,
        extension_heartbeat_monitor: ExtensionHeartbeatMonitor | None = None,
        internet_settings_service=None,
    ):
        super().__init__()
        self._runtime = runtime
        self._settings_manager = settings_manager
        self._browser_session_manager = browser_session_manager
        self._browser_session_watcher: BrowserSessionWatcher | None = None
        self._extension_heartbeat_monitor = extension_heartbeat_monitor
        self._permitted_browsers = frozenset({"chrome.exe"})
        self._kill_browsers_on_startup_enabled = True
        self._tray_app = None
        self._web_session_reason: str = ""
        self._web_session_choice: str = ""
        self._web_session_verse_title: str = ""
        self._web_session_urls: list[str] = []
        self._web_session_duration_seconds: int | None = None
        self._web_session_heartbeat_grace_deadline: float | None = None
        self._extension_launch_check_timer: QTimer | None = None
        self._panic_elevated: bool = False
        self._panic_last_override_count: int = 0
        self._panic_reminders = None  # initialised lazily on first use
        self._bible_library = None     # initialised lazily on first use
        self._prayer_recipient_library = None  # initialised lazily on first use
        self._streak = None            # initialised lazily on first use
        self._diet_state = None        # initialised lazily on first use
        self._streak_badge_lbl = None
        self._prayer_tool_win = None    # lazy; opened via Tools menu
        self._encouragement_editor_win = None  # lazy; opened via Tools menu
        self._internet_settings_win = None  # lazy; opened via Tools menu
        self._internet_settings_service = internet_settings_service
        self._active_panic_session: PanicSession | None = None
        self._active_panic_window: QWidget | None = None
        self._supervisor_down_alerted: bool = False
        self._supervisor_heartbeat_grace_deadline: float = 0.0
        self._supervisor_seen_healthy: bool = False
        self._supervisor_heartbeat_reader: HeartbeatReader | None = None
        self.setWindowTitle("Purity — Prototype")
        self.resize(1280, 800)
        self._popup_mgr = PopupManager()
        self._review_win: ReviewWindow | None = None
        self._notes_browser: NotesBrowserWindow | None = None
        self._log_viewer_win: PurityLogViewerWindow | None = None
        self._pulse_manager: PulseManager | None = None
        self._pulse_notes_writer = notes_writer

        # Kick off BibleLibrary's file load in the background so its I/O overlaps
        # with _build_ui() instead of adding to it serially; joined below before use.
        self._bible_library_load_thread: threading.Thread | None = None
        if self._runtime is not None:
            from services.bible_library import BibleLibrary

            def _load_bible_library() -> None:
                self._bible_library = BibleLibrary(self._runtime.data_root)

            self._bible_library_load_thread = threading.Thread(
                target=_load_bible_library, daemon=True
            )
            self._bible_library_load_thread.start()

        _init_started_at = time.perf_counter()

        def _log_init_step(step: str) -> None:
            print(f"[MainWindow.__init__] {step} at +{(time.perf_counter() - _init_started_at) * 1000:.1f} ms", flush=True)

        self._apply_live_settings_from_manager()
        _log_init_step("_apply_live_settings_from_manager done")

        if self._runtime is not None:
            self._pulse_notes_writer = make_notes_writer(run_id=self._runtime.session.run_id)
        _log_init_step("make_notes_writer done")

        # Log normalizer sink — register before _build_ui so the sink is ready.
        self._log_sink = PurityLogNormalizerSink()
        if runtime is not None:
            runtime.journal._sinks.append(self._log_sink)
        _log_init_step("log sink registered")

        self._center_on_screen()
        self._build_menu_bar()
        _log_init_step("_build_menu_bar done")
        self._build_ui()
        _log_init_step("_build_ui done")

        # Eagerly initialize BibleLibrary so the left-dock dashboard can source memorizing verses.
        if self._bible_library_load_thread is not None:
            self._bible_library_load_thread.join()
        elif self._bible_library is None and self._runtime is not None:
            from services.bible_library import BibleLibrary
            self._bible_library = BibleLibrary(self._runtime.data_root)
        _log_init_step("BibleLibrary loaded")

        # Left-edge sliding dashboard — kept as a top-level tool window.
        self._left_dock = LeftDockDashboard(bible_library=self._bible_library, main_window=self)
        self._left_dock.show()
        _log_init_step("LeftDockDashboard shown")

        # Web session timer pill — hidden until a session is approved.
        self._web_timer_pill = WebTimerPill(parent=None)
        self._web_timer_pill.set_main_window(self)
        self._web_timer_pill.session_expired.connect(self._on_web_session_expired)
        self._web_timer_pill.extension_warning_expired.connect(self._on_extension_warning_expired)
        _log_init_step("WebTimerPill set up")

        # Persistent panic button — always visible, bottom-right of primary screen.
        self._panic_btn = PanicButton(parent=None)
        self._panic_btn.panic_requested.connect(self._start_panic_intervention)
        _log_init_step("PanicButton set up")

        self._web_watcher = WebWatcherService(parent=self)
        self._web_watcher.web_opened.connect(self._on_web_opened)  # type: ignore[arg-type]
        self._web_watcher.browser_running_changed.connect(self._on_browser_running_changed)
        self._web_request_timer_ready = False
        self._kill_browsers_on_startup()
        self._web_watcher.start()
        _log_init_step("WebWatcherService started")

        if self._browser_session_manager is not None or self._extension_heartbeat_monitor is not None:
            self._browser_session_watcher = BrowserSessionWatcher(
                session_manager=self._browser_session_manager,
                heartbeat_monitor=self._extension_heartbeat_monitor,
                parent=self,
            )
            self._browser_session_watcher.session_payload_changed.connect(self._poll_panic_elevation)
            self._browser_session_watcher.heartbeat_healthy_changed.connect(self._enforce_extension_heartbeat)
            self._browser_session_watcher.start()
        _log_init_step("BrowserSessionWatcher started")

        # 60-second heartbeat tick: note_clock + system.alive journal event
        if self._runtime is not None:
            self._alive_timer = QTimer(self)
            self._alive_timer.timeout.connect(self._tick_alive)
            self._alive_timer.start(60_000)

            self._web_request_timer = QTimer(self)
            self._web_request_timer.timeout.connect(self._process_web_launch_requests)
            self._web_request_timer.start(500)

            self._app_control_request_timer = QTimer(self)
            self._app_control_request_timer.timeout.connect(self._process_app_control_requests)
            self._app_control_request_timer.start(500)

            if self._settings_manager is not None:
                self._pulse_manager = PulseManager(
                    data_root=self._runtime.data_root,
                    settings_manager=self._settings_manager,
                    activity_monitor=UserActivityMonitor(
                        clock_fn=lambda: datetime.now().astimezone(),
                    ),
                    journal=self._runtime.journal,
                )
                self._pulse_timer = QTimer(self)
                self._pulse_timer.timeout.connect(self._poll_pulse_due)
                self._pulse_timer.start(5_000)

            # Supervisor watchdog health check.
            # Grace period is reset to 0 so the check is active immediately;
            # the check itself skips alerting until it has seen at least one
            # healthy heartbeat (supervisor_seen_healthy flag).
            self._supervisor_heartbeat_grace_deadline = 0.0
            self._supervisor_seen_healthy: bool = False
            _hb_dir = self._runtime.data_root / "_system" / "purity" / "heartbeats"
            self._supervisor_heartbeat_reader = HeartbeatReader(
                heartbeats_dir=_hb_dir,
                stale_s=_SUPERVISOR_STALE_S,
                dead_s=_SUPERVISOR_DEAD_S,
            )
            self._supervisor_health_timer = QTimer(self)
            self._supervisor_health_timer.timeout.connect(self._check_supervisor_heartbeat)
            self._supervisor_health_timer.start(10_000)
            QTimer.singleShot(0, self._check_supervisor_heartbeat)
        _log_init_step("__init__ complete")

    def _build_ui(self):
        _build_ui_started_at = time.perf_counter()
        root = QWidget()
        root.setProperty("class", "windowBackground")
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._build_header())
        print(f"[MainWindow._build_ui] _build_header done at +{(time.perf_counter() - _build_ui_started_at) * 1000:.1f} ms", flush=True)

        body = QWidget()
        body.setProperty("class", "transparent")
        hbox = QHBoxLayout(body)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        hbox.addWidget(ReflectionDashboard(), stretch=1)
        print(f"[MainWindow._build_ui] ReflectionDashboard done at +{(time.perf_counter() - _build_ui_started_at) * 1000:.1f} ms", flush=True)
        hbox.addWidget(self._build_sidebar(), stretch=0)
        print(f"[MainWindow._build_ui] _build_sidebar done at +{(time.perf_counter() - _build_ui_started_at) * 1000:.1f} ms", flush=True)
        vbox.addWidget(body, stretch=1)

        self.setCentralWidget(root)

    def _log_ui_timer_duration(self, callback_name: str, started_at: float) -> None:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if elapsed_ms < _UI_TIMER_LAG_THRESHOLD_MS:
            return
        if self._runtime is None:
            return
        _append_startup_log(
            self._runtime.data_root,
            f"UI timer callback slow: {callback_name} took {elapsed_ms:.1f} ms",
        )

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        preferences_action = QAction("Preferences", self)
        preferences_action.setEnabled(self._settings_manager is not None)
        preferences_action.triggered.connect(self._open_preferences)
        file_menu.addAction(preferences_action)

        tools_menu = menu_bar.addMenu("Tools")

        view_journals_action = QAction("View Journals", self)
        view_journals_action.triggered.connect(self._open_log_viewer)
        tools_menu.addAction(view_journals_action)

        edit_encouragements_action = QAction("Edit Encouragements", self)
        edit_encouragements_action.setEnabled(self._runtime is not None)
        edit_encouragements_action.triggered.connect(self._open_encouragement_editor)
        tools_menu.addAction(edit_encouragements_action)

        bible_browser_action = QAction("Bible Browser", self)
        bible_browser_action.setEnabled(self._runtime is not None)
        bible_browser_action.triggered.connect(self._open_bible_browser)
        tools_menu.addAction(bible_browser_action)

        launch_pulse_action = QAction("Launch Pulse", self)
        launch_pulse_action.triggered.connect(self._launch_manual_pulse)
        tools_menu.addAction(launch_pulse_action)

        reset_streak_action = QAction("Reset Streak", self)
        reset_streak_action.triggered.connect(self._reset_streak)
        tools_menu.addAction(reset_streak_action)

        prayer_tool_action = QAction("Prayer Tool", self)
        prayer_tool_action.setEnabled(self._runtime is not None)
        prayer_tool_action.triggered.connect(self._open_prayer_tool)
        tools_menu.addAction(prayer_tool_action)

        internet_settings_action = QAction("Internet Settings", self)
        internet_settings_action.setEnabled(self._internet_settings_service is not None)
        internet_settings_action.triggered.connect(self._open_internet_settings)
        tools_menu.addAction(internet_settings_action)

        debug_menu = menu_bar.addMenu("Debug")

        expire_web_action = QAction("Expire Web Session", self)
        expire_web_action.triggered.connect(self._debug_expire_web_session)
        debug_menu.addAction(expire_web_action)

        honor_dialog_action = QAction("Test Honor Dialog", self)
        honor_dialog_action.triggered.connect(self._debug_web_session_honor_dialog)
        debug_menu.addAction(honor_dialog_action)

        open_logs_folder_action = QAction("Open Logs Folder", self)
        open_logs_folder_action.setEnabled(self._runtime is not None)
        open_logs_folder_action.triggered.connect(self._open_logs_folder)
        debug_menu.addAction(open_logs_folder_action)

    def _open_encouragement_editor(self) -> None:
        from services.bible_library import BibleLibrary
        from services.panic_reminders import PanicReminders
        from ui.tools.encouragement_editor_dialog import EncouragementEditorDialog

        if self._panic_reminders is None and self._runtime is not None:
            self._panic_reminders = PanicReminders(self._runtime.data_root)
        if self._bible_library is None and self._runtime is not None:
            self._bible_library = BibleLibrary(self._runtime.data_root)
        if self._panic_reminders is None or self._bible_library is None:
            return

        if self._encouragement_editor_win is None:
            self._encouragement_editor_win = EncouragementEditorDialog(
                self._panic_reminders, self._bible_library, parent=None
            )
            # Clear the reference when the window is closed so it can be
            # garbage-collected and a fresh instance is created on next open.
            self._encouragement_editor_win.finished.connect(
                lambda _: setattr(self, "_encouragement_editor_win", None)
            )

        self._encouragement_editor_win.show()
        self._encouragement_editor_win.raise_()
        self._encouragement_editor_win.activateWindow()

    def _get_streak_service(self):
        if self._streak is None and self._runtime is not None:
            self._streak = PurityStreak(self._runtime.data_root)
        return self._streak

    def _get_streak_days(self) -> int:
        streak = self._get_streak_service()
        return streak.get_days() if streak is not None else 0

    def _reset_streak(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset Streak",
            "Are you sure you want to reset your streak to 0?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        streak = self._get_streak_service()
        if streak is not None:
            streak.reset()
        self._refresh_streak_badges()

    def _refresh_streak_badges(self) -> None:
        days = self._get_streak_days()
        if self._streak_badge_lbl is not None:
            self._streak_badge_lbl.setText(f"\U0001f525 Day {days}")
        if self._left_dock is not None:
            self._left_dock.refresh_streak_badge()

    def _get_prayer_recipient_library(self):
        from services.prayer_recipients import PrayerRecipientLibrary

        if self._prayer_recipient_library is None and self._runtime is not None:
            self._prayer_recipient_library = PrayerRecipientLibrary(self._runtime.data_root)
        return self._prayer_recipient_library

    def _get_diet_state(self):
        from services.diet_state import DietState

        if self._diet_state is None and self._runtime is not None:
            self._diet_state = DietState(self._runtime.data_root)
        return self._diet_state

    def _get_daily_calorie_budget(self) -> int:
        if self._settings_manager is None:
            return 2000
        return int(self._settings_manager.get("app.diet", "daily_calories") or 2000)

    def _open_prayer_tool(self) -> None:
        from ui.tools.prayer_tool_dialog import PrayerToolDialog

        library = self._get_prayer_recipient_library()
        if library is None:
            return

        if self._prayer_tool_win is None:
            self._prayer_tool_win = PrayerToolDialog(library, parent=None)
            self._prayer_tool_win.finished.connect(
                lambda _: setattr(self, "_prayer_tool_win", None)
            )

        self._prayer_tool_win.show()
        self._prayer_tool_win.raise_()
        self._prayer_tool_win.activateWindow()

    def _open_internet_settings(self) -> None:
        from ui.tools.internet_settings_dialog import InternetSettingsDialog

        if self._internet_settings_service is None:
            return

        if self._internet_settings_win is None:
            self._internet_settings_win = InternetSettingsDialog(
                self._internet_settings_service, parent=None
            )
            self._internet_settings_win.finished.connect(
                lambda _: setattr(self, "_internet_settings_win", None)
            )

        self._internet_settings_win.show()
        self._internet_settings_win.raise_()
        self._internet_settings_win.activateWindow()

    def _open_bible_browser(self) -> None:
        from services.bible_library import BibleLibrary
        from ui.tools.bible_browser_dialog import BibleBrowserDialog

        if self._bible_library is None and self._runtime is not None:
            self._bible_library = BibleLibrary(self._runtime.data_root)
        if self._bible_library is None:
            return

        dlg = BibleBrowserDialog(
            bible_library=self._bible_library,
            select_mode=False,
            parent=None,
        )
        dlg.exec()

    def _open_logs_folder(self) -> None:
        import subprocess
        if self._runtime is None:
            return
        logs_path = self._runtime.data_root / "_system" / "purity"
        logs_path.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(logs_path)])

    def _debug_expire_web_session(self) -> None:
        self._web_timer_pill.stop_session()
        self._on_web_session_expired()

    def _debug_web_session_honor_dialog(self) -> None:
        self._show_web_session_honor_dialog()

    def _apply_live_settings_from_manager(self) -> None:
        if self._settings_manager is None:
            self._permitted_browsers = frozenset({"chrome.exe"})
            self._kill_browsers_on_startup_enabled = True
            return

        self._permitted_browsers = get_permitted_browsers(self._settings_manager) - {"msedge.exe"}
        self._kill_browsers_on_startup_enabled = get_kill_browsers_on_startup(
            self._settings_manager
        )

    def _build_header(self) -> QWidget:
        state = MockAppState()
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(
            f"background-color: {COLOR_SURFACE};"
            f"border-bottom: 1px solid {COLOR_BORDER};"
        )
        row = QHBoxLayout(header)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(16)

        # App name
        app_name = QLabel("Purity")
        app_name.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_LARGE}pt;"
            f"font-weight: 800; color: {COLOR_ACCENT}; background: transparent;"
        )
        row.addWidget(app_name)

        row.addStretch()

        # Verse snippet
        verse = state.today_verse
        verse_lbl = QLabel(f"\"{verse['text'][:60]}…\"  — {verse['reference']}")
        verse_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"font-style: italic; color: {COLOR_TEXT_MUTED}; background: transparent;"
        )
        row.addWidget(verse_lbl)

        row.addStretch()

        # Streak badge
        streak_badge = QLabel(f"🔥 Day {self._get_streak_days()}")
        streak_badge.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"font-weight: 700; color: {COLOR_TEXT};"
            f"background-color: {COLOR_SURFACE_2}; border-radius: 10px;"
            f"padding: 3px 10px;"
        )
        row.addWidget(streak_badge)
        self._streak_badge_lbl = streak_badge

        # Clock (updates every 60 s)
        self._clock_lbl = QLabel()
        self._clock_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"color: {COLOR_TEXT_MUTED}; background: transparent; min-width: 56px;"
        )
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._update_clock()
        row.addWidget(self._clock_lbl)

        timer = QTimer(self)
        timer.timeout.connect(self._update_clock)
        timer.start(60_000)

        return header

    def _update_clock(self):
        self._clock_lbl.setText(datetime.now().strftime("%H:%M"))
        if self._streak_badge_lbl is not None:
            self._streak_badge_lbl.setText(f"\U0001f525 Day {self._get_streak_days()}")

    def _build_sidebar(self) -> QGroupBox:
        sidebar = QGroupBox("Demo Triggers")
        sidebar.setFixedWidth(170)
        sidebar.setStyleSheet(
            f"QGroupBox {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border-left: 1px solid {COLOR_BORDER};"
            f"  border-radius: 0px;"
            f"  margin-top: 0px;"
            f"  padding: 4px 0px 4px 0px;"
            f"  font-size: {FONT_SIZE_SMALL}pt;"
            f"}}"
            f"QGroupBox::title {{"
            f"  subcontrol-origin: margin;"
            f"  subcontrol-position: top center;"
            f"  padding: 0 4px;"
            f"}}"
        )
        outer = QVBoxLayout(sidebar)
        outer.setContentsMargins(0, 14, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)
        vbox = QVBoxLayout(inner)
        vbox.setSpacing(6)
        vbox.setContentsMargins(6, 4, 6, 4)

        for label, popup_type in _POPUP_BUTTONS:
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda checked, pt=popup_type: self._popup_mgr.trigger(pt)
            )
            vbox.addWidget(btn)

        review_btn = QPushButton("Open Review")
        review_btn.clicked.connect(self._open_review)
        vbox.addWidget(review_btn)

        vbox.addSpacing(8)

        add_note_btn = QPushButton("📝 Add Note")
        add_note_btn.clicked.connect(self._open_note_dialog)
        vbox.addWidget(add_note_btn)

        browse_notes_btn = QPushButton("📂 Browse Notes")
        browse_notes_btn.clicked.connect(self._open_notes_browser)
        vbox.addWidget(browse_notes_btn)

        pulse_btn = QPushButton("Pulse")
        pulse_btn.clicked.connect(self._launch_manual_pulse)
        vbox.addWidget(pulse_btn)

        log_btn = QPushButton("📋 Journal Viewer")
        log_btn.clicked.connect(self._open_log_viewer)
        vbox.addWidget(log_btn)

        vbox.addSpacing(8)

        tg_shutdown_btn = QPushButton("📨 TG: Shutdown")
        tg_shutdown_btn.clicked.connect(self._test_telegram_shutdown)
        vbox.addWidget(tg_shutdown_btn)

        tg_crash_btn = QPushButton("📨 TG: App Down")
        tg_crash_btn.clicked.connect(self._test_telegram_app_down)
        vbox.addWidget(tg_crash_btn)

        tg_supervisor_btn = QPushButton("📨 TG: Supervisor Down")
        tg_supervisor_btn.clicked.connect(self._test_telegram_supervisor_shutdown)
        vbox.addWidget(tg_supervisor_btn)

        honor_debug_btn = QPushButton("🧪 Honor Dialog")
        honor_debug_btn.clicked.connect(self._debug_web_session_honor_dialog)
        vbox.addWidget(honor_debug_btn)

        bible_browser_btn = QPushButton("📖 Bible Browser")
        bible_browser_btn.clicked.connect(self._open_bible_browser)
        vbox.addWidget(bible_browser_btn)

        calorie_test_btn = QPushButton("🍔 Test Calorie API")
        calorie_test_btn.clicked.connect(self._test_calorie_estimate)
        vbox.addWidget(calorie_test_btn)

        vbox.addStretch()
        return sidebar  # type: ignore[return-value]

    def _tick_alive(self):
        """Fired every 60 s: update run-tail clock and emit system.alive."""
        import time as _time
        from services.journal_events import emit_system_alive
        if self._runtime is not None:
            self._runtime.tail.note_clock(_time.time())
            emit_system_alive(self._runtime.journal)

    def _kill_browsers_on_startup(self):
        """Kill any browsers already open when the app launches so the watcher starts fresh.

        Runs on a background thread since taskkill spawns are slow; web-launch-request
        approval is gated on completion (see ``_on_browser_kill_finished``) so a
        legitimately-approved shortcut launch can't race a stale-browser kill.
        """
        if not self._kill_browsers_on_startup_enabled:
            self._web_request_timer_ready = True
            return
        from services.web_watcher import _WATCHED_BROWSERS
        self._browser_kill_thread = QThread(self)
        self._browser_kill_worker = _BrowserKillWorker(list(_WATCHED_BROWSERS))
        self._browser_kill_worker.moveToThread(self._browser_kill_thread)
        self._browser_kill_thread.started.connect(self._browser_kill_worker.run)
        self._browser_kill_worker.finished.connect(self._on_browser_kill_finished)
        self._browser_kill_worker.finished.connect(self._browser_kill_thread.quit)
        self._browser_kill_worker.finished.connect(self._browser_kill_worker.deleteLater)
        self._browser_kill_thread.finished.connect(self._browser_kill_thread.deleteLater)
        self._browser_kill_thread.start()

    def _on_browser_kill_finished(self) -> None:
        self._web_request_timer_ready = True

    def _on_web_opened(self, exe: str):
        """Intercept browser opens: minimize it, then restore or kill based on user choice."""
        from shane_common.processes.windows import (
            list_process_pids,
            enum_visible_windows_for_pids,
            minimize_windows,
            restore_windows,
            taskkill_processes,
        )
        from services.journal_events import emit_chrome_opened, emit_chrome_decision
        from services.web_watcher import _WATCHED_BROWSERS

        exe_lower = str(exe).strip().lower()
        if exe_lower == "msedge.exe":
            # Edge is never permitted — kill it immediately without showing any popup.
            taskkill_processes(["msedge.exe"])
            self._web_timer_pill.stop_session()
            self._clear_browser_session_state()
            if self._runtime is not None:
                emit_chrome_opened(self._runtime.journal, pid_count=0)
                emit_chrome_decision(
                    self._runtime.journal,
                    allowed=False,
                    choice="",
                    reason="",
                )
            return

        permitted = exe_lower in self._permitted_browsers
        minimized_hwnds: list = []

        def _get_browser_pids():
            return [pid for exe in _WATCHED_BROWSERS for pid in list_process_pids(exe)]

        def _minimize_browser_windows():
            pids = _get_browser_pids()
            if pids:
                new_hwnds = [h for h in enum_visible_windows_for_pids(pids)
                             if h not in minimized_hwnds]
                minimized_hwnds.extend(minimize_windows(new_hwnds))

        _minimize_browser_windows()

        if self._runtime is not None:
            emit_chrome_opened(self._runtime.journal, pid_count=len(_get_browser_pids()))

        _data_root = self._runtime.data_root if self._runtime is not None else None
        popup = WebPopup(permitted=permitted, parent=self, data_root=_data_root)
        # Browser windows may not exist yet at detection time; retry as they appear.
        QTimer.singleShot(300, _minimize_browser_windows)
        QTimer.singleShot(800, _minimize_browser_windows)
        QTimer.singleShot(1500, _minimize_browser_windows)
        if permitted:
            # Auto-accept immediately — no fields required, popup just flashes and closes.
            QTimer.singleShot(0, popup._on_commit)
        result = popup.exec()
        selected_choice = popup.selected_choice
        reason_text = popup.reason_text
        allowed_urls = list(popup.allowed_urls)

        if result == QDialog.DialogCode.Accepted:
            restore_windows(minimized_hwnds)
            self._web_session_reason = reason_text
            self._web_session_choice = selected_choice
            self._web_session_verse_title = getattr(popup, "verse_title", "")
            self._web_session_urls = allowed_urls
            self._web_session_duration_seconds = None
            self._start_browser_session_state(choice=selected_choice, allowed_urls=allowed_urls, duration_seconds=86_400)
            write_launcher_approved_marker()
            if self._runtime is not None:
                from services.url_history import UrlHistory
                UrlHistory(self._runtime.data_root).record_urls(allowed_urls)
                emit_chrome_decision(
                    self._runtime.journal,
                    allowed=True,
                    choice=selected_choice,
                    reason=reason_text,
                )
            self._start_extension_launch_check()

            # Show a random web-flagged encouragement before resuming the session.
            if self._panic_reminders is None and self._runtime is not None:
                from services.panic_reminders import PanicReminders
                self._panic_reminders = PanicReminders(self._runtime.data_root)
            if self._bible_library is None and self._runtime is not None:
                from services.bible_library import BibleLibrary
                self._bible_library = BibleLibrary(self._runtime.data_root)
            web_reminder = (
                self._panic_reminders.get_random_web()
                if self._panic_reminders is not None
                else None
            )
            if web_reminder is not None:
                from ui.intervention.encouragement_preview import show_encouragement_preview
                show_encouragement_preview(web_reminder, self._bible_library, parent=None)
                self._web_session_verse_title = web_reminder.get("title", "") or self._web_session_verse_title

            self._web_timer_pill.set_session_title(self._web_session_verse_title)
            self._web_timer_pill.show_static()
        else:
            taskkill_processes(list(_WATCHED_BROWSERS))
            self._web_timer_pill.stop_session()
            self._clear_browser_session_state()
            if self._runtime is not None:
                emit_chrome_decision(
                    self._runtime.journal,
                    allowed=False,
                    choice=selected_choice,
                    reason=reason_text,
                )

    def _poll_panic_elevation(self, payload: dict | None = None) -> None:
        """Poll the active browser session for override-counter changes.

        When the override_count increases the danger state is elevated and
        panic.danger_elevated is emitted.  When the session clears while still
        elevated, panic.danger_cleared is emitted and the flag is reset.
        """
        started_at = time.perf_counter()
        if payload is None and self._browser_session_manager is None:
            self._log_ui_timer_duration("_poll_panic_elevation", started_at)
            return

        try:
            if payload is None:
                payload = self._browser_session_manager.get_session_payload()
            session_active = bool(payload.get("is_active"))
            override_count = int(payload.get("override_count") or 0)

            if session_active and override_count > self._panic_last_override_count:
                self._panic_last_override_count = override_count
                self._panic_elevated = True
                if self._runtime is not None:
                    from services.journal_events import emit_panic_danger_elevated
                    emit_panic_danger_elevated(
                        self._runtime.journal,
                        panic_session_id="none",
                        override_url=str(payload.get("last_override_url") or ""),
                    )
            elif not session_active and self._panic_elevated:
                self._panic_elevated = False
                self._panic_last_override_count = 0
                if self._runtime is not None:
                    from services.journal_events import emit_panic_danger_cleared
                    emit_panic_danger_cleared(
                        self._runtime.journal,
                        panic_session_id="none",
                    )

            self._panic_btn.set_elevated(self._panic_elevated)
        finally:
            self._log_ui_timer_duration("_poll_panic_elevation", started_at)

    def _start_panic_intervention(self) -> None:
        """Immediate browser-kill + session-clear; open the reason dialog.

        If a panic session is already active and its window is still visible,
        raise that window and return without creating a new session.
        """
        from shane_common.processes.windows import taskkill_processes
        from services.web_watcher import _WATCHED_BROWSERS
        from services.journal_events import emit_panic_started

        # --- Guard: one session at a time ---
        if self._active_panic_session is not None:
            if self._active_panic_window is not None and self._active_panic_window.isVisible():
                self._active_panic_window.raise_()
                self._active_panic_window.activateWindow()
                return

        # --- 1. Create session in INTERRUPTING state ---
        session = PanicSession()

        # --- 2. Capture elevated flag ---
        session.started_while_elevated = self._panic_elevated

        # --- 3. Kill browsers + clear web state ---
        taskkill_processes(list(_WATCHED_BROWSERS))
        self._web_timer_pill.stop_session()
        if self._browser_session_manager is not None:
            self._browser_session_manager.clear_session()
        self._web_session_reason = ""
        self._web_session_choice = ""
        self._web_session_urls = []
        self._web_session_duration_seconds = None
        self._web_session_heartbeat_grace_deadline = None

        # --- 4. Emit panic.started ---
        if self._runtime is not None:
            emit_panic_started(
                self._runtime.journal,
                panic_session_id=session.panic_session_id,
                started_while_elevated=session.started_while_elevated,
            )

        # --- 5. Advance to SELECTING_REASONS ---
        session.start_reason_selection()
        self._active_panic_session = session

        # Open PanicReasonDialog → on accept, launch intervention window.
        from ui.intervention.panic_reason_dialog import PanicReasonDialog
        from ui.intervention.panic_intervention_window import PanicInterventionWindow

        stats = getattr(self, "_panic_stats", None)

        if self._panic_reminders is None and self._runtime is not None:
            from services.panic_reminders import PanicReminders
            self._panic_reminders = PanicReminders(self._runtime.data_root)
        if self._bible_library is None and self._runtime is not None:
            from services.bible_library import BibleLibrary
            self._bible_library = BibleLibrary(self._runtime.data_root)
        reminder = (
            self._panic_reminders.get_random()
            if self._panic_reminders is not None
            else None
        )

        reason_dialog = PanicReasonDialog(
            stats=stats, reminder=reminder,
            bible_library=self._bible_library, parent=None
        )
        if reason_dialog.exec() != QDialog.DialogCode.Accepted:
            # User closed the reason dialog without selecting — record abandoned.
            from services.journal_events import emit_panic_closed
            try:
                session.close(PanicSessionOutcome.ABANDONED)
            except Exception:
                traceback.print_exc()
            if self._runtime is not None:
                try:
                    emit_panic_closed(
                        self._runtime.journal,
                        panic_session_id=session.panic_session_id,
                        outcome=PanicSessionOutcome.ABANDONED.value,
                    )
                except Exception:
                    traceback.print_exc()
            self._active_panic_session = None
            self._active_panic_window = None
            return

        session.selected_reason_ids = reason_dialog.selected_reason_ids

        # Record reasons in stats and emit journal event.
        if stats is not None:
            try:
                stats.record_reasons(session.selected_reason_ids)
            except Exception:
                traceback.print_exc()
        if self._runtime is not None:
            from services.journal_events import emit_panic_reasons_selected
            emit_panic_reasons_selected(
                self._runtime.journal,
                panic_session_id=session.panic_session_id,
                reason_ids=session.selected_reason_ids,
            )

        intervention_window = PanicInterventionWindow(
            session=session,
            runtime=self._runtime,
            parent=None,
        )
        self._active_panic_window = intervention_window
        intervention_window.show()

    def _process_web_launch_requests(self) -> None:
        started_at = time.perf_counter()
        if self._runtime is None:
            self._log_ui_timer_duration("_process_web_launch_requests", started_at)
            return
        if not self._web_request_timer_ready:
            self._log_ui_timer_duration("_process_web_launch_requests", started_at)
            return

        try:
            try:
                pending = read_pending_web_launch_requests(self._runtime.data_root)
            except Exception as exc:
                append_web_request_log(
                    self._runtime.data_root,
                    "app.poll_failed",
                    "Running app failed while reading web launch requests.",
                    level="ERROR",
                    exc=exc,
                )
                return

            for path, request in pending:
                try:
                    mark_web_launch_request_done(path)
                    args = request.get("args") if isinstance(request, dict) else []
                    if not isinstance(args, list):
                        append_web_request_log(
                            self._runtime.data_root,
                            "app.request_args_invalid",
                            "Web launch request args were not a list.",
                            level="ERROR",
                            details={"path": str(path), "args_type": type(args).__name__},
                        )
                        args = []
                    self._handle_web_launch_request([str(arg) for arg in args])
                except Exception as exc:
                    append_web_request_log(
                        self._runtime.data_root,
                        "app.request_failed",
                        "Running app failed while processing web launch request.",
                        level="ERROR",
                        details={"path": str(path), "request": request},
                        exc=exc,
                    )
        finally:
            self._log_ui_timer_duration("_process_web_launch_requests", started_at)

    def _handle_web_launch_request(self, args: list[str]) -> None:
        from services.journal_events import emit_chrome_decision

        if self._runtime is not None:
            append_web_request_log(
                self._runtime.data_root,
                "app.request_handling_started",
                "Running app is handling queued web launch request.",
                details={"args": list(args), "run_id": self._runtime.session.run_id},
            )

        popup = WebPopup(permitted=True, parent=self, data_root=self._runtime.data_root if self._runtime is not None else None)
        # Auto-accept immediately — no fields required, popup just flashes and closes.
        QTimer.singleShot(0, popup._on_commit)
        popup.exec()
        selected_choice = popup.selected_choice
        reason_text = popup.reason_text
        allowed_urls = list(popup.allowed_urls)
        duration_seconds = int(popup.duration_seconds)

        if self._runtime is not None:
            emit_chrome_decision(
                self._runtime.journal,
                allowed=True,
                choice=selected_choice,
                reason=reason_text,
            )
        self._web_session_reason = reason_text
        self._web_session_choice = selected_choice
        self._web_session_verse_title = getattr(popup, "verse_title", "")
        self._web_session_urls = allowed_urls
        self._web_session_duration_seconds = duration_seconds
        self._start_browser_session_state(choice=selected_choice, allowed_urls=allowed_urls, duration_seconds=86_400)
        if self._runtime is not None:
            from services.url_history import UrlHistory
            UrlHistory(self._runtime.data_root).record_urls(allowed_urls)
        write_launcher_approved_marker()

        # Show a random web-flagged encouragement before launching Chrome.
        if self._panic_reminders is None and self._runtime is not None:
            from services.panic_reminders import PanicReminders
            self._panic_reminders = PanicReminders(self._runtime.data_root)
        if self._bible_library is None and self._runtime is not None:
            from services.bible_library import BibleLibrary
            self._bible_library = BibleLibrary(self._runtime.data_root)
        web_reminder = (
            self._panic_reminders.get_random_web()
            if self._panic_reminders is not None
            else None
        )
        if web_reminder is not None:
            from ui.intervention.encouragement_preview import show_encouragement_preview
            show_encouragement_preview(web_reminder, self._bible_library, parent=None)
            self._web_session_verse_title = web_reminder.get("title", "") or self._web_session_verse_title

        chrome = _find_chrome()
        if chrome:
            proc = subprocess.Popen([str(chrome)] + list(args))
        else:
            proc = subprocess.Popen(["chrome"] + list(args), shell=True)
        self._start_extension_launch_check()
        if self._runtime is not None:
            append_web_request_log(
                self._runtime.data_root,
                "app.chrome_started",
                "Chrome was started for approved web launch request.",
                details={
                    "pid": proc.pid,
                    "args": list(args),
                    "choice": selected_choice,
                    "reason": reason_text,
                    "allowed_urls": allowed_urls,
                    "verse_title": self._web_session_verse_title,
                },
            )
        self._web_timer_pill.set_session_title(self._web_session_verse_title)
        self._web_timer_pill.show_static()

    def _start_browser_session_state(
        self,
        *,
        choice: str,
        allowed_urls: list[str],
        duration_seconds: int,
    ) -> None:
        if self._browser_session_manager is None:
            return
        if self._extension_heartbeat_monitor is not None:
            self._extension_heartbeat_monitor.clear()
        self._browser_session_manager.start_session(
            purpose=choice,
            allowed_urls=allowed_urls,
            duration_seconds=duration_seconds,
        )
        self._web_session_heartbeat_grace_deadline = time.monotonic() + _EXTENSION_HEARTBEAT_GRACE_SECONDS

    def _clear_browser_session_state(self) -> None:
        self._web_session_urls = []
        self._web_session_duration_seconds = None
        self._web_session_heartbeat_grace_deadline = None
        self._cancel_extension_launch_check()
        if self._browser_session_manager is None:
            return
        self._browser_session_manager.clear_session()

    def _start_extension_launch_check(self) -> None:
        """Start a one-shot 5-second timer; if the extension hasn't sent a heartbeat
        by then, the browser session is killed immediately."""
        self._cancel_extension_launch_check()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._check_extension_at_launch)
        timer.start(5_000)
        self._extension_launch_check_timer = timer

    def _cancel_extension_launch_check(self) -> None:
        if self._extension_launch_check_timer is not None:
            self._extension_launch_check_timer.stop()
            self._extension_launch_check_timer = None

    def _check_extension_at_launch(self) -> None:
        self._extension_launch_check_timer = None
        is_healthy = self._extension_heartbeat_monitor is None or self._extension_heartbeat_monitor.is_healthy()
        if bool(is_healthy) or self._extension_heartbeat_grace_active():
            return
        if self._runtime is not None:
            append_web_request_log(
                self._runtime.data_root,
                "extension_heartbeat.launch_check_failed",
                "Extension not detected 5 seconds after Chrome opened — starting warning countdown.",
                level="WARN",
            )
        if not self._web_timer_pill.is_warning_active:
            self._web_timer_pill.start_extension_warning(30)

    def _extension_heartbeat_grace_active(self) -> bool:
        deadline = self._web_session_heartbeat_grace_deadline
        return deadline is not None and time.monotonic() < deadline

    def _show_extension_heartbeat_warning(self, message: str) -> None:
        QMessageBox.warning(self, "Purity Extension Unavailable", message)

    def _stop_browser_session_for_extension_failure(self, *, message: str, log_event: str) -> None:
        from shane_common.processes.windows import taskkill_processes
        from services.web_watcher import _WATCHED_BROWSERS

        taskkill_processes(list(_WATCHED_BROWSERS))
        self._web_timer_pill.stop_session()
        self._web_session_reason = ""
        self._web_session_choice = ""
        self._clear_browser_session_state()
        if self._runtime is not None:
            append_web_request_log(
                self._runtime.data_root,
                log_event,
                message,
                level="WARN",
            )
        self._show_extension_heartbeat_warning(message)

    def _on_extension_warning_expired(self) -> None:
        self._stop_browser_session_for_extension_failure(
            message=(
                "The Chrome enforcement extension did not respond within the warning period. "
                "The browser session was ended."
            ),
            log_event="extension_heartbeat.warning_expired",
        )

    def _enforce_extension_heartbeat(self, is_healthy: bool | None = None) -> None:
        started_at = time.perf_counter()
        if not self._web_timer_pill.isVisible():
            self._log_ui_timer_duration("_enforce_extension_heartbeat", started_at)
            return
        try:
            if is_healthy is None:
                is_healthy = self._extension_heartbeat_monitor is None or self._extension_heartbeat_monitor.is_healthy()
            healthy = bool(is_healthy) or self._extension_heartbeat_grace_active()
            if healthy:
                if self._web_timer_pill.is_warning_active:
                    self._web_timer_pill.clear_extension_warning()
                return
            if not self._web_timer_pill.is_warning_active:
                self._web_timer_pill.start_extension_warning(30)
        finally:
            self._log_ui_timer_duration("_enforce_extension_heartbeat", started_at)

    def _start_web_timer(self, timeout: int | None = None) -> None:
        """Read the configured timeout and (re)start the session pill."""
        if timeout is None:
            timeout = 300
            try:
                mgr = self._settings_manager
                if mgr is None:
                    mgr = build_purity_settings_manager()
                timeout = get_web_session_timeout_seconds(mgr)
            except Exception:
                traceback.print_exc()
        self._web_timer_pill.set_session_title(self._web_session_verse_title)
        self._web_timer_pill.set_timeout(timeout)
        self._web_timer_pill.start_session()

    def _on_web_session_expired(self) -> None:
        """Called when the timer pill countdown reaches zero."""
        from shane_common.processes.windows import taskkill_processes
        from services.web_watcher import _WATCHED_BROWSERS
        from ui.intervention.session_extend_popup import SessionExtendPopup
        popup = SessionExtendPopup(
            choice=self._web_session_choice,
            reason=self._web_session_reason,
            parent=self,
        )
        if popup.exec() == QDialog.DialogCode.Accepted:
            self._start_browser_session_state(
                choice=self._web_session_choice,
                allowed_urls=list(self._web_session_urls),
                duration_seconds=self._web_session_duration_seconds or 300,
            )
            self._start_web_timer(self._web_session_duration_seconds)
        else:
            taskkill_processes(list(_WATCHED_BROWSERS))
            self._web_timer_pill.stop_session()
            self._web_session_reason = ""
            self._web_session_choice = ""
            self._clear_browser_session_state()
            self._show_web_session_honor_dialog()

    def _on_browser_running_changed(self, is_running: bool) -> None:
        """React to worker-thread browser state updates without UI-thread polling."""
        if not self._web_timer_pill.isVisible():
            return
        if is_running:
            return
        self._web_timer_pill.stop_session()
        self._clear_browser_session_state()
        self._show_web_session_honor_dialog()

    def _show_web_session_honor_dialog(self) -> None:
        """Show the post-session accountability dialog: did you honor God online?"""
        from ui.intervention.web_session_honor_dialog import WebSessionHonorDialog
        from services.telegram_notify import build_telegram_adapter_from_settings

        def _reach_out() -> None:
            if self._settings_manager is None:
                return
            telegram = build_telegram_adapter_from_settings(
                self._settings_manager,
                format_message=format_notification_details,
            )
            telegram.send(make_web_session_reach_out_event(reason=""))

        dlg = WebSessionHonorDialog(reach_out_callback=_reach_out)
        dlg.exec()

    def _open_review(self):
        if self._review_win is not None and self._review_win.isVisible():
            self._review_win.raise_()
            self._review_win.activateWindow()
            return
        self._review_win = ReviewWindow(parent=self)
        self._review_win.show()

    def _open_note_dialog(self):
        NoteDialog(writer=notes_writer, owner="purity", parent=self).exec()

    def _poll_pulse_due(self) -> None:
        started_at = time.perf_counter()
        if self._pulse_manager is None:
            self._log_ui_timer_duration("_poll_pulse_due", started_at)
            return
        try:
            pending = self._pulse_manager.poll_due_pulse()
            if pending is None:
                return
            self._open_pulse_dialog(pending)
        finally:
            self._log_ui_timer_duration("_poll_pulse_due", started_at)

    def _launch_manual_pulse(self) -> None:
        if self._pulse_manager is None:
            return
        pending = self._pulse_manager.create_manual_pulse()
        if pending is None:
            return
        self._open_pulse_dialog(pending)

    def _build_prayer_session_names(self) -> list[str]:
        library = self._get_prayer_recipient_library()
        names = library.get_available_names() if library is not None else []
        count = 2
        if self._settings_manager is not None:
            count = get_prayer_recipients_per_session(self._settings_manager)
        return random.sample(names, min(count, len(names))) if names else []

    def _mark_prayer_recipient_prayed(self, name: str) -> None:
        library = self._get_prayer_recipient_library()
        if library is not None:
            library.mark_prayed(name)

    def _start_new_prayer_session(self) -> None:
        self._left_dock.start_prayer_session(self._build_prayer_session_names())

    def _open_pulse_dialog(self, pending) -> None:
        self._left_dock.start_prayer_session(self._build_prayer_session_names())
        self._left_dock.retry_failed_diet_calories()
        self._left_dock.expand()
        self._handle_pulse_submit(
            pending,
            sliders=PulseSliders(),
            answers={},
            note_text="",
            reach_out_text="",
            reach_out_sent=False,
            evening_duration_choice=None,
        )

    def _handle_pulse_submit(
        self,
        pending,
        *,
        sliders,
        answers,
        note_text,
        reach_out_text,
        reach_out_sent,
        evening_duration_choice,
    ) -> None:
        if self._pulse_manager is None:
            return
        self._pulse_manager.submit_pulse(
            pending=pending,
            sliders=sliders,
            answers=answers,
            note_text=note_text,
            reach_out_text=reach_out_text,
            reach_out_sent=reach_out_sent,
            evening_duration_choice=evening_duration_choice,
        )

    def _handle_pulse_note_submit(self, pending, note_text: str) -> None:
        note = self._pulse_notes_writer.build_note(
            note_type=NoteType.GENERAL,
            text=note_text,
            context={
                "feature": "pulse",
                "pulse_id": pending.pulse_id,
                "pulse_kind": pending.pulse_kind.value,
            },
        )
        self._pulse_notes_writer.commit(note)
        if self._runtime is not None:
            from services.journal_events import emit_note_created

            emit_note_created(self._runtime.journal, owner="pulse")
        if self._pulse_manager is not None:
            self._pulse_manager.submit_note(
                pulse_id=pending.pulse_id,
                pulse_kind=pending.pulse_kind,
            )

    def _handle_pulse_reach_out(self, pending, sliders, message: str) -> None:
        if self._settings_manager is None:
            return
        telegram = build_telegram_adapter_from_settings(
            self._settings_manager,
            format_message=format_notification_details,
        )
        telegram.send(
            make_pulse_reach_out_event(
                sliders=sliders,
                user_message=message,
            )
        )
        if self._pulse_manager is not None:
            self._pulse_manager.record_reach_out(
                pulse_id=pending.pulse_id,
                pulse_kind=pending.pulse_kind,
            )

    def _open_notes_browser(self):
        if self._notes_browser is None:
            self._notes_browser = NotesBrowserWindow(repository=notes_repo, parent=self)
            self._notes_browser.set_writer(notes_writer)
        self._notes_browser.show()
        self._notes_browser.raise_()
        self._notes_browser.activateWindow()
        self._notes_browser.refresh()

    def _open_log_viewer(self):
        if self._log_viewer_win is None:
            data_root = self._runtime.data_root if self._runtime is not None else None
            self._log_viewer_win = PurityLogViewerWindow(
                sink=self._log_sink, data_root=data_root, parent=None
            )
            self._log_sink.emitter.log_row_appended.connect(
                self._log_viewer_win.append_row
            )
        self._log_viewer_win.show()
        self._log_viewer_win.raise_()
        self._log_viewer_win.activateWindow()

    def _open_preferences(self) -> None:
        if self._settings_manager is None:
            return

        previous_data_root = resolve_purity_data_root(self._settings_manager, environ={})
        dialog = PreferencesDialog(self._settings_manager, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._apply_live_settings_from_manager()

        new_data_root = resolve_purity_data_root(self._settings_manager, environ={})
        if new_data_root != previous_data_root:
            QMessageBox.information(
                self,
                "Restart Required",
                "The Data Root preference was saved, but it will only take effect after restarting Purity.",
            )

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())

    def attach_tray_app(self, tray_app) -> None:
        self._tray_app = tray_app

    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _process_app_control_requests(self) -> None:
        started_at = time.perf_counter()
        if self._runtime is None:
            self._log_ui_timer_duration("_process_app_control_requests", started_at)
            return

        try:
            try:
                pending = read_pending_app_control_requests(self._runtime.data_root)
            except Exception as exc:
                append_web_request_log(
                    self._runtime.data_root,
                    "app_control.poll_failed",
                    "Running app failed while reading app control requests.",
                    level="ERROR",
                    exc=exc,
                )
                return

            for path, request in pending:
                try:
                    mark_app_control_request_done(path)
                    action = str(request.get("action") or "") if isinstance(request, dict) else ""
                    if action == "show_main_window":
                        append_web_request_log(
                            self._runtime.data_root,
                            "app_control.show_main_window",
                            "Running app is raising the main window for a duplicate launch.",
                            details={"path": str(path), "request": request},
                        )
                        self.show_and_raise()
                    else:
                        append_web_request_log(
                            self._runtime.data_root,
                            "app_control.unknown_action",
                            "Running app ignored unknown app control request.",
                            level="WARN",
                            details={"path": str(path), "request": request},
                        )
                except Exception as exc:
                    append_web_request_log(
                        self._runtime.data_root,
                        "app_control.request_failed",
                        "Running app failed while processing app control request.",
                        level="ERROR",
                        details={"path": str(path), "request": request},
                        exc=exc,
                    )
        finally:
            self._log_ui_timer_duration("_process_app_control_requests", started_at)

    # ------------------------------------------------------------------
    # Supervisor watchdog monitoring
    # ------------------------------------------------------------------

    def _check_supervisor_heartbeat(self) -> None:
        """Periodic check — alert if the supervisor process is unresponsive."""
        started_at = time.perf_counter()
        if self._supervisor_heartbeat_reader is None:
            self._log_ui_timer_duration("_check_supervisor_heartbeat", started_at)
            return
        try:
            try:
                _, mtime, exit_present = self._supervisor_heartbeat_reader.read("purity_supervisor")

                # Not yet seen a healthy heartbeat — wait for the supervisor to start.
                # Once we've seen it healthy at least once, any subsequent absence is an alert.
                supervisor_is_down = (
                    exit_present
                    or mtime is None
                    or self._supervisor_heartbeat_reader.is_dead(mtime)
                )

                if not supervisor_is_down:
                    self._supervisor_seen_healthy = True
                    self._supervisor_down_alerted = False
                    return

                # Still waiting for supervisor to write its first heartbeat.
                if not self._supervisor_seen_healthy:
                    return

                if not self._supervisor_down_alerted:
                    self._supervisor_down_alerted = True
                    self._notify_supervisor_down()
                    self._show_supervisor_down_dialog()

            except Exception as exc:
                _append_startup_log(
                    self._runtime.data_root,
                    f"_check_supervisor_heartbeat: unhandled exception: {exc}",
                )
        finally:
            self._log_ui_timer_duration("_check_supervisor_heartbeat", started_at)

    def _notify_supervisor_down(self) -> None:
        """Send a Telegram notification that the supervisor is down."""
        import os, urllib.parse, urllib.request
        if self._settings_manager is None:
            return
        token = os.environ.get("PURITY_TELEGRAM_TOKEN", "").strip()
        chat_ids_str = str(self._settings_manager.get("app.telegram", "telegram_chat_ids") or "")
        chat_ids = [c.strip() for c in chat_ids_str.split(",") if c.strip()]
        if not token or not chat_ids:
            return
        text = "[WARNING] purity_supervisor.down\nscope=global\ndetails=reason=heartbeat.dead"
        for chat_id in chat_ids:
            try:
                params = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
                req = urllib.request.Request(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data=params, method="POST",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp.read()
            except Exception:
                traceback.print_exc()

    def _show_supervisor_down_dialog(self) -> None:
        """Show a warning dialog and offer to relaunch the supervisor."""
        # Use no parent so the dialog appears regardless of MainWindow visibility.
        dlg = QMessageBox()
        dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setWindowTitle("Purity Supervisor Down")
        dlg.setText("The Purity Supervisor is down.")
        dlg.setInformativeText(
            "The watchdog supervisor process is not responding. "
            "Purity is running unguarded. Click Relaunch to restart the supervisor."
        )
        relaunch_btn = dlg.addButton("Relaunch Supervisor", QMessageBox.ButtonRole.AcceptRole)
        dlg.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        dlg.exec()
        if dlg.clickedButton() is relaunch_btn and self._runtime is not None:
            _launch_supervisor(self._runtime.data_root)
            self._supervisor_seen_healthy = False
            self._supervisor_down_alerted = False

    # ------------------------------------------------------------------
    # Telegram test buttons
    # ------------------------------------------------------------------

    def _send_test_telegram(self, kind: str, details: str) -> None:
        import os
        import urllib.parse
        import urllib.request

        if self._settings_manager is None:
            QMessageBox.warning(self, "Telegram Test", "No settings manager available.")
            return

        token = os.environ.get("PURITY_TELEGRAM_TOKEN", "").strip()
        chat_ids_str = str(self._settings_manager.get("app.telegram", "telegram_chat_ids") or "")
        chat_ids = [c.strip() for c in chat_ids_str.split(",") if c.strip()]

        if not token:
            QMessageBox.warning(
                self, "Telegram Test",
                "PURITY_TELEGRAM_TOKEN env var is not set.\n\nSet it and restart Purity."
            )
            return
        if not chat_ids:
            QMessageBox.warning(
                self, "Telegram Test",
                "No chat IDs configured.\n\nSet telegram_chat_ids in Preferences → app.telegram."
            )
            return

        text = f"[TEST] {kind}\ndetails={details}"
        errors = []
        for chat_id in chat_ids:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            params = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
            req = urllib.request.Request(url, data=params, method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp.read()
            except Exception as exc:
                errors.append(f"chat_id={chat_id}: {exc}")

        if errors:
            QMessageBox.warning(self, "Telegram Test", "Send failed:\n\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "Telegram Test", f"Sent to {len(chat_ids)} chat(s): {kind}")

    def _test_telegram_shutdown(self) -> None:
        self._send_test_telegram("purity_app.shutdown", details="reason=test.button")

    def _test_telegram_app_down(self) -> None:
        self._send_test_telegram("purity_app.down", details="reason=test.button")

    def _test_telegram_supervisor_shutdown(self) -> None:
        self._send_test_telegram("purity_supervisor.shutdown", details="reason=test.button")

    def _test_calorie_estimate(self) -> None:
        from services.openai_client import CalorieEstimationError, estimate_calories

        test_food = "one medium banana and a cup of black coffee"
        try:
            calories = estimate_calories(test_food)
        except CalorieEstimationError as exc:
            QMessageBox.warning(self, "Calorie Estimate Failed", str(exc))
            return
        except Exception:
            traceback.print_exc()
            QMessageBox.warning(self, "Calorie Estimate Failed", "Unexpected error; see logs.")
            return
        QMessageBox.information(
            self,
            "Calorie Estimate",
            f"Food: {test_food}\nEstimated calories: {calories:.0f}",
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        app = QApplication.instance()
        if app is None or app.closingDown():
            if self._browser_session_watcher is not None:
                self._browser_session_watcher.stop()
            self._web_watcher.stop()
            # Best-effort: record ABANDONED if a panic session is still open.
            if (
                self._active_panic_session is not None
                and self._active_panic_session.state != PanicSessionState.CLOSED
            ):
                from services.journal_events import emit_panic_closed

                try:
                    self._active_panic_session.close(PanicSessionOutcome.ABANDONED)
                except Exception:
                    traceback.print_exc()
                if self._runtime is not None:
                    try:
                        emit_panic_closed(
                            self._runtime.journal,
                            panic_session_id=self._active_panic_session.panic_session_id,
                            outcome=PanicSessionOutcome.ABANDONED.value,
                        )
                    except Exception:
                        traceback.print_exc()
            super().closeEvent(event)
            return

        event.ignore()
        self.hide()
