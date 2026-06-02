"""Purity application main window.

This module contains ``MainWindow`` and the helper utilities it relies on
(supervisor launcher, startup-log writer, Chrome finder).  Kept separate from
``app.py`` so that the startup/singleton logic there stays small and focused.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
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
    QVBoxLayout,
    QWidget,
)
from shane_common.preferences.manager import SettingsManager
from shane_common.ui.preferences.preferences_dialog import PreferencesDialog
from shane_common.watchdog.heartbeat_reader import HeartbeatReader
from services.browser_session import BrowserSessionManager, ExtensionHeartbeatMonitor
from services.mock_state import MockAppState
from services.notes_setup import notes_writer, notes_repo
from services.panic_session import PanicSession, PanicSessionOutcome, PanicSessionState
from services.settings_schemas import (
    build_purity_settings_manager,
    get_kill_browsers_on_startup,
    get_permitted_browsers,
    get_web_session_timeout_seconds,
    resolve_purity_data_root,
)
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

_EXTENSION_HEARTBEAT_GRACE_SECONDS = 20.0

# ---------------------------------------------------------------------------
# Supervisor watchdog constants
# ---------------------------------------------------------------------------
_SUPERVISOR_HEARTBEAT_GRACE_SECONDS = 30.0
_SUPERVISOR_STALE_S = 15.0
_SUPERVISOR_DEAD_S = 30.0

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
    creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    try:
        subprocess.Popen(cmd, creationflags=creationflags)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(
        self,
        runtime=None,
        settings_manager: SettingsManager | None = None,
        browser_session_manager: BrowserSessionManager | None = None,
        extension_heartbeat_monitor: ExtensionHeartbeatMonitor | None = None,
    ):
        super().__init__()
        self._runtime = runtime
        self._settings_manager = settings_manager
        self._browser_session_manager = browser_session_manager
        self._extension_heartbeat_monitor = extension_heartbeat_monitor
        self._permitted_browsers = frozenset({"chrome.exe"})
        self._kill_browsers_on_startup_enabled = True
        self._tray_app = None
        self._web_session_reason: str = ""
        self._web_session_choice: str = ""
        self._web_session_urls: list[str] = []
        self._web_session_duration_seconds: int | None = None
        self._web_session_heartbeat_grace_deadline: float | None = None
        self._panic_elevated: bool = False
        self._panic_last_override_count: int = 0
        self._panic_reminders = None  # initialised lazily on first use
        self._encouragement_editor_win = None  # lazy; opened via Tools menu
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

        self._apply_live_settings_from_manager()

        # Log normalizer sink — register before _build_ui so the sink is ready.
        self._log_sink = PurityLogNormalizerSink()
        if runtime is not None:
            runtime.journal._sinks.append(self._log_sink)

        self._center_on_screen()
        self._build_menu_bar()
        self._build_ui()

        # Web session timer pill — hidden until a session is approved.
        self._web_timer_pill = WebTimerPill(parent=None)
        self._web_timer_pill.set_main_window(self)
        self._web_timer_pill.session_expired.connect(self._on_web_session_expired)
        self._web_timer_pill.extension_warning_expired.connect(self._on_extension_warning_expired)

        # Persistent panic button — always visible, bottom-right of primary screen.
        self._panic_btn = PanicButton(parent=None)
        self._panic_btn.panic_requested.connect(self._start_panic_intervention)

        self._web_watcher = WebWatcherService(parent=self)
        self._web_watcher.web_opened.connect(self._on_web_opened)  # type: ignore[arg-type]
        self._kill_browsers_on_startup()
        self._web_watcher.start()

        # Poll every 5 s to hide the pill when the watched browser has been closed.
        self._browser_poll_timer = QTimer(self)
        self._browser_poll_timer.timeout.connect(self._poll_browser_running)
        self._browser_poll_timer.start(5_000)

        self._extension_health_timer = QTimer(self)
        self._extension_health_timer.timeout.connect(self._enforce_extension_heartbeat)
        self._extension_health_timer.start(10_000)

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

            self._panic_elevation_timer = QTimer(self)
            self._panic_elevation_timer.timeout.connect(self._poll_panic_elevation)
            self._panic_elevation_timer.start(500)

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

    def _build_ui(self):
        root = QWidget()
        root.setProperty("class", "windowBackground")
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._build_header())

        body = QWidget()
        body.setProperty("class", "transparent")
        hbox = QHBoxLayout(body)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        hbox.addWidget(ReflectionDashboard(), stretch=1)
        hbox.addWidget(self._build_sidebar(), stretch=0)
        vbox.addWidget(body, stretch=1)

        self.setCentralWidget(root)

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

        debug_menu = menu_bar.addMenu("Debug")

        expire_web_action = QAction("Expire Web Session", self)
        expire_web_action.triggered.connect(self._debug_expire_web_session)
        debug_menu.addAction(expire_web_action)

    def _open_encouragement_editor(self) -> None:
        from services.panic_reminders import PanicReminders
        from ui.tools.encouragement_editor_dialog import EncouragementEditorDialog

        if self._panic_reminders is None and self._runtime is not None:
            self._panic_reminders = PanicReminders(self._runtime.data_root)
        if self._panic_reminders is None:
            return

        if self._encouragement_editor_win is None:
            self._encouragement_editor_win = EncouragementEditorDialog(
                self._panic_reminders, parent=self
            )
            # Clear the reference when the window is closed so it can be
            # garbage-collected and a fresh instance is created on next open.
            self._encouragement_editor_win.finished.connect(
                lambda _: setattr(self, "_encouragement_editor_win", None)
            )

        self._encouragement_editor_win.show()
        self._encouragement_editor_win.raise_()
        self._encouragement_editor_win.activateWindow()

    def _debug_expire_web_session(self) -> None:
        self._web_timer_pill.stop_session()
        self._on_web_session_expired()

    def _apply_live_settings_from_manager(self) -> None:
        if self._settings_manager is None:
            self._permitted_browsers = frozenset({"chrome.exe"})
            self._kill_browsers_on_startup_enabled = True
            return

        self._permitted_browsers = get_permitted_browsers(self._settings_manager)
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
        streak_badge = QLabel(f"🔥 Day {state.purity_streak_days}")
        streak_badge.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"font-weight: 700; color: {COLOR_TEXT};"
            f"background-color: {COLOR_SURFACE_2}; border-radius: 10px;"
            f"padding: 3px 10px;"
        )
        row.addWidget(streak_badge)

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

    def _build_sidebar(self) -> QGroupBox:
        sidebar = QGroupBox("Demo Triggers")
        sidebar.setFixedWidth(160)
        sidebar.setStyleSheet(
            f"QGroupBox {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border-left: 1px solid {COLOR_BORDER};"
            f"  border-radius: 0px;"
            f"  margin-top: 0px;"
            f"  padding: 12px 8px 8px 8px;"
            f"  font-size: {FONT_SIZE_SMALL}pt;"
            f"}}"
            f"QGroupBox::title {{"
            f"  subcontrol-origin: margin;"
            f"  subcontrol-position: top center;"
            f"  padding: 0 4px;"
            f"}}"
        )
        vbox = QVBoxLayout(sidebar)
        vbox.setSpacing(8)
        vbox.setContentsMargins(8, 16, 8, 8)

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

        log_btn = QPushButton("📋 Journal Viewer")
        log_btn.clicked.connect(self._open_log_viewer)
        vbox.addWidget(log_btn)

        vbox.addStretch()
        return sidebar

    def _tick_alive(self):
        """Fired every 60 s: update run-tail clock and emit system.alive."""
        import time as _time
        from services.journal_events import emit_system_alive
        if self._runtime is not None:
            self._runtime.tail.note_clock(_time.time())
            emit_system_alive(self._runtime.journal)

    def _kill_browsers_on_startup(self):
        """Kill any browsers already open when the app launches so the watcher starts fresh."""
        if not self._kill_browsers_on_startup_enabled:
            return
        from shane_common.processes.windows import taskkill_processes
        from services.web_watcher import _WATCHED_BROWSERS
        taskkill_processes(list(_WATCHED_BROWSERS))

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

        permitted = str(exe).strip().lower() in self._permitted_browsers
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
        result = popup.exec()
        selected_choice = popup.selected_choice
        reason_text = popup.reason_text
        allowed_urls = list(popup.allowed_urls)
        duration_seconds = int(popup.duration_seconds)

        if result == QDialog.DialogCode.Accepted:
            restore_windows(minimized_hwnds)
            self._web_session_reason = reason_text
            self._web_session_choice = selected_choice
            self._web_session_urls = allowed_urls
            self._web_session_duration_seconds = duration_seconds
            self._start_browser_session_state(choice=selected_choice, allowed_urls=allowed_urls, duration_seconds=duration_seconds)
            if self._runtime is not None:
                from services.url_history import UrlHistory
                UrlHistory(self._runtime.data_root).record_urls(allowed_urls)
                emit_chrome_decision(
                    self._runtime.journal,
                    allowed=True,
                    choice=selected_choice,
                    reason=reason_text,
                )
            self._start_web_timer(duration_seconds)
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

    def _poll_panic_elevation(self) -> None:
        """Poll the active browser session for override-counter changes.

        When the override_count increases the danger state is elevated and
        panic.danger_elevated is emitted.  When the session clears while still
        elevated, panic.danger_cleared is emitted and the flag is reset.
        """
        if self._browser_session_manager is None:
            return

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
        reminder = (
            self._panic_reminders.get_random()
            if self._panic_reminders is not None
            else None
        )

        reason_dialog = PanicReasonDialog(stats=stats, reminder=reminder, parent=None)
        if reason_dialog.exec() != QDialog.DialogCode.Accepted:
            # User closed the reason dialog without selecting — record abandoned.
            from services.journal_events import emit_panic_closed
            try:
                session.close(PanicSessionOutcome.ABANDONED)
            except Exception:
                pass
            if self._runtime is not None:
                try:
                    emit_panic_closed(
                        self._runtime.journal,
                        panic_session_id=session.panic_session_id,
                        outcome=PanicSessionOutcome.ABANDONED.value,
                    )
                except Exception:
                    pass
            self._active_panic_session = None
            self._active_panic_window = None
            return

        session.selected_reason_ids = reason_dialog.selected_reason_ids

        # Record reasons in stats and emit journal event.
        if stats is not None:
            try:
                stats.record_reasons(session.selected_reason_ids)
            except Exception:
                pass
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
        if self._runtime is None:
            return

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
        result = popup.exec()
        selected_choice = popup.selected_choice
        reason_text = popup.reason_text
        allowed_urls = list(popup.allowed_urls)
        duration_seconds = int(popup.duration_seconds)

        if result == QDialog.DialogCode.Accepted:
            if self._runtime is not None:
                emit_chrome_decision(
                    self._runtime.journal,
                    allowed=True,
                    choice=selected_choice,
                    reason=reason_text,
                )
            self._web_session_reason = reason_text
            self._web_session_choice = selected_choice
            self._web_session_urls = allowed_urls
            self._web_session_duration_seconds = duration_seconds
            self._start_browser_session_state(choice=selected_choice, allowed_urls=allowed_urls, duration_seconds=duration_seconds)
            if self._runtime is not None:
                from services.url_history import UrlHistory
                UrlHistory(self._runtime.data_root).record_urls(allowed_urls)
            write_launcher_approved_marker()
            chrome = _find_chrome()
            if chrome:
                proc = subprocess.Popen([str(chrome)] + list(args))
            else:
                proc = subprocess.Popen(["chrome"] + list(args), shell=True)
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
                        "duration_seconds": duration_seconds,
                    },
                )
            self._start_web_timer(duration_seconds)
            return

        self._web_timer_pill.stop_session()
        self._clear_browser_session_state()
        if self._runtime is not None:
            emit_chrome_decision(
                self._runtime.journal,
                allowed=False,
                choice=selected_choice,
                reason=reason_text,
            )
            append_web_request_log(
                self._runtime.data_root,
                "app.request_blocked",
                "Queued web launch request was blocked or cancelled.",
                details={
                    "choice": selected_choice,
                    "reason": reason_text,
                    "allowed_urls": allowed_urls,
                    "duration_seconds": duration_seconds,
                },
            )

    def _start_browser_session_state(
        self,
        *,
        choice: str,
        allowed_urls: list[str],
        duration_seconds: int,
    ) -> None:
        if self._browser_session_manager is None:
            return
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
        if self._browser_session_manager is None:
            return
        self._browser_session_manager.clear_session()

    def _extension_heartbeat_is_healthy(self) -> bool:
        if self._extension_heartbeat_monitor is None:
            return True
        return self._extension_heartbeat_monitor.is_healthy()

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

    def _enforce_extension_heartbeat(self) -> None:
        if not self._web_timer_pill.isVisible():
            return
        healthy = self._extension_heartbeat_is_healthy() or self._extension_heartbeat_grace_active()
        if healthy:
            if self._web_timer_pill.is_warning_active:
                self._web_timer_pill.clear_extension_warning()
            return
        if not self._web_timer_pill.is_warning_active:
            self._web_timer_pill.start_extension_warning(30)

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
                pass
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

    def _poll_browser_running(self) -> None:
        """Hide the pill if no watched browser processes are running."""
        if not self._web_timer_pill.isVisible():
            return
        from shane_common.processes.windows import list_process_pids
        from services.web_watcher import _WATCHED_BROWSERS
        any_running = any(
            list_process_pids(exe) for exe in _WATCHED_BROWSERS
        )
        if not any_running:
            self._web_timer_pill.stop_session()
            self._clear_browser_session_state()

    def _open_review(self):
        if self._review_win is not None and self._review_win.isVisible():
            self._review_win.raise_()
            self._review_win.activateWindow()
            return
        self._review_win = ReviewWindow(parent=self)
        self._review_win.show()

    def _open_note_dialog(self):
        NoteDialog(writer=notes_writer, owner="purity", parent=self).exec()

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
        if self._runtime is None:
            return

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

    # ------------------------------------------------------------------
    # Supervisor watchdog monitoring
    # ------------------------------------------------------------------

    def _check_supervisor_heartbeat(self) -> None:
        """Periodic check — alert if the supervisor process is unresponsive."""
        if self._supervisor_heartbeat_reader is None:
            return
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
                self._show_supervisor_down_dialog()

        except Exception as exc:
            _append_startup_log(
                self._runtime.data_root,
                f"_check_supervisor_heartbeat: unhandled exception: {exc}",
            )

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

    def closeEvent(self, event) -> None:  # type: ignore[override]
        app = QApplication.instance()
        if app is None or app.closingDown():
            # Best-effort: record ABANDONED if a panic session is still open.
            if (
                self._active_panic_session is not None
                and self._active_panic_session.state != PanicSessionState.CLOSED
            ):
                from services.journal_events import emit_panic_closed

                try:
                    self._active_panic_session.close(PanicSessionOutcome.ABANDONED)
                except Exception:
                    pass
                if self._runtime is not None:
                    try:
                        emit_panic_closed(
                            self._runtime.journal,
                            panic_session_id=self._active_panic_session.panic_session_id,
                            outcome=PanicSessionOutcome.ABANDONED.value,
                        )
                    except Exception:
                        pass
            super().closeEvent(event)
            return

        event.ignore()
        self.hide()
