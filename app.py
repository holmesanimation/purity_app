# PySide6 UX Prototype — entry point
# Original app logic preserved in reminder_dialog.py, chrome_dialog.py,
# focus_guard.py, focus_guard_chrome_trigger.py (untouched).

import sys
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QDialog, QMainWindow, QMessageBox,
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from styles.theme import (
    GLOBAL_QSS, COLOR_ACCENT, COLOR_ACCENT_LIGHT, COLOR_SURFACE, COLOR_BORDER,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_BACKGROUND, COLOR_SURFACE_2,
    FONT_FAMILY, FONT_SIZE_SMALL, FONT_SIZE_NORMAL, FONT_SIZE_MEDIUM, FONT_SIZE_LARGE,
)
from services.mock_state import MockAppState
from services.notes_setup import notes_writer, notes_repo
from ui.reflection.dashboard import ReflectionDashboard
from ui.intervention.popup_manager import PopupManager
from ui.intervention.web_popup import WebPopup
from services.web_watcher import WebWatcherService
from services.web_requests import (
    append_web_request_log,
    mark_web_launch_request_done,
    read_pending_web_launch_requests,
    write_launcher_approved_marker,
)
from ui.review.review_window import ReviewWindow
from ui.notes_context_menu import NotesContextMenuFilter
from ui.notes.note_dialog import NoteDialog
from ui.notes.notes_browser_window import NotesBrowserWindow
from gui.log_normalizer_sink import PurityLogNormalizerSink
from gui.log_viewer_window import PurityLogViewerWindow

_POPUP_BUTTONS = [
    ("Fire: Web",     "web"),
    ("Fire: Prayer",  "prayer"),
    ("Fire: Risk",    "risk"),
    ("Fire: Hourly",  "hourly"),
    ("Fire: Evening", "evening"),
]

# Browsers the user is allowed to open. All others are blocked immediately.
# Hardcoded until the config mechanism is integrated.
_PERMITTED_BROWSERS: frozenset[str] = frozenset({'chrome.exe'})

_CHROME_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
]


def _is_pid_running(pid: object) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False

    if pid <= 0:
        return False

    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                creationflags=creationflags,
                timeout=5,
            )
        except Exception:
            return False

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("INFO:"):
                continue
            parts = [part.strip('"') for part in line.split('","')]
            if len(parts) >= 2:
                try:
                    return int(parts[1]) == pid
                except ValueError:
                    continue
        return False

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _taskkill_pid(pid: int) -> bool:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=10,
        )
    except Exception:
        return False
    return not _is_pid_running(pid)


def _find_running_instance(data_root):
    from services.supervisor_client import PuritySupervisorClient

    client = PuritySupervisorClient(data_root)
    heartbeat, mtime, exit_present = client.heartbeat_reader.read("purity_app")
    if heartbeat is None or mtime is None:
        return None
    if client.heartbeat_reader.is_dead(mtime):
        return None

    pid = heartbeat.get("pid") if isinstance(heartbeat, dict) else None
    if not _is_pid_running(pid):
        return None

    # A stale exit marker from a previous clean shutdown should not hide a
    # fresh heartbeat from the currently running app.
    if exit_present:
        try:
            exit_marker = client.heartbeats_dir / "purity_app.exit_marker.json"
            if exit_marker.exists() and exit_marker.stat().st_mtime > mtime:
                return None
        except OSError:
            return None

    state = "stale" if client.heartbeat_reader.is_stale(mtime) else "running"
    return {"pid": int(pid), "state": state}


def _prompt_for_running_instance(existing_instance: dict) -> bool:
    pid = existing_instance["pid"]
    state = existing_instance["state"]

    dialog = QMessageBox()
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setWindowTitle("Purity Already Running")
    dialog.setText("Purity appears to already be running in the background.")
    dialog.setInformativeText(
        f"Detected PID {pid} with a {state} heartbeat. "
        "Choose Keep Running to leave the current instance alone and cancel this launch, "
        "or Restart to stop it and start a fresh instance."
    )
    keep_running_btn = dialog.addButton("Keep Running", QMessageBox.ButtonRole.RejectRole)
    restart_btn = dialog.addButton("Restart", QMessageBox.ButtonRole.AcceptRole)
    dialog.setDefaultButton(restart_btn)
    dialog.exec()
    return dialog.clickedButton() is restart_btn


def _restart_running_instance(existing_instance: dict) -> bool:
    pid = existing_instance["pid"]
    if not _taskkill_pid(pid):
        return False

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not _is_pid_running(pid):
            return True
        time.sleep(0.1)
    return not _is_pid_running(pid)


def _show_restart_failed(pid: int) -> None:
    QMessageBox.critical(
        None,
        "Purity Restart Failed",
        (
            "Purity could not stop the existing background instance "
            f"(PID {pid}). Close it manually, then launch Purity again."
        ),
    )


def _find_chrome() -> Path | None:
    for path in _CHROME_PATHS:
        if path.exists():
            return path
    return None


class MainWindow(QMainWindow):
    def __init__(self, runtime=None):
        super().__init__()
        self._runtime = runtime
        self._tray_app = None
        self.setWindowTitle("Purity — Prototype")
        self.resize(1280, 800)
        self._popup_mgr = PopupManager()
        self._review_win: ReviewWindow | None = None
        self._notes_browser: NotesBrowserWindow | None = None
        self._log_viewer_win: PurityLogViewerWindow | None = None

        # Log normalizer sink — register before _build_ui so the sink is ready.
        self._log_sink = PurityLogNormalizerSink()
        if runtime is not None:
            runtime.journal._sinks.append(self._log_sink)

        self._center_on_screen()
        self._build_menu_bar()
        self._build_ui()

        self._web_watcher = WebWatcherService(parent=self)
        self._web_watcher.web_opened.connect(self._on_web_opened)  # type: ignore[arg-type]
        self._kill_browsers_on_startup()
        self._web_watcher.start()

        # 60-second heartbeat tick: note_clock + system.alive journal event
        if self._runtime is not None:
            self._alive_timer = QTimer(self)
            self._alive_timer.timeout.connect(self._tick_alive)
            self._alive_timer.start(60_000)

            self._web_request_timer = QTimer(self)
            self._web_request_timer.timeout.connect(self._process_web_launch_requests)
            self._web_request_timer.start(500)

    def _build_ui(self):
        root = QWidget()
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._build_header())

        body = QWidget()
        hbox = QHBoxLayout(body)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        hbox.addWidget(ReflectionDashboard(), stretch=1)
        hbox.addWidget(self._build_sidebar(), stretch=0)
        vbox.addWidget(body, stretch=1)

        self.setCentralWidget(root)

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        tools_menu = menu_bar.addMenu("Tools")

        view_journals_action = QAction("View Journals", self)
        view_journals_action.triggered.connect(self._open_log_viewer)
        tools_menu.addAction(view_journals_action)

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

        permitted = exe in _PERMITTED_BROWSERS
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

        popup = WebPopup(permitted=permitted, parent=self)
        # Browser windows may not exist yet at detection time; retry as they appear.
        QTimer.singleShot(300, _minimize_browser_windows)
        QTimer.singleShot(800, _minimize_browser_windows)
        QTimer.singleShot(1500, _minimize_browser_windows)
        result = popup.exec()
        selected_choice = popup.selected_choice
        reason_text = popup.reason_text

        if result == QDialog.DialogCode.Accepted:
            restore_windows(minimized_hwnds)
            if self._runtime is not None:
                emit_chrome_decision(
                    self._runtime.journal,
                    allowed=True,
                    choice=selected_choice,
                    reason=reason_text,
                )
        else:
            taskkill_processes(list(_WATCHED_BROWSERS))
            if self._runtime is not None:
                emit_chrome_decision(
                    self._runtime.journal,
                    allowed=False,
                    choice=selected_choice,
                    reason=reason_text,
                )

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

        popup = WebPopup(permitted=True, parent=self)
        result = popup.exec()
        selected_choice = popup.selected_choice
        reason_text = popup.reason_text

        if result == QDialog.DialogCode.Accepted:
            if self._runtime is not None:
                emit_chrome_decision(
                    self._runtime.journal,
                    allowed=True,
                    choice=selected_choice,
                    reason=reason_text,
                )
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
                    },
                )
            return

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
                details={"choice": selected_choice, "reason": reason_text},
            )

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

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())

    def attach_tray_app(self, tray_app) -> None:
        self._tray_app = tray_app

    def closeEvent(self, event) -> None:  # type: ignore[override]
        app = QApplication.instance()
        if app is None or app.closingDown():
            super().closeEvent(event)
            return

        event.ignore()
        self.hide()
        if self._tray_app is not None:
            self._tray_app.notify_running(
                "Purity is still running in the system tray. Use the tray icon to reopen it.",
                title="Purity Hidden to Tray",
            )


def main():
    from pathlib import Path
    from services.runtime import create_purity_runtime
    from services.journal_events import emit_app_started, emit_app_stopped
    from gui.supervisor_tray import PurityTrayApp

    # Resolve data_root before QApplication so all paths are stable at startup.
    data_root = Path(os.environ.get("PURITY_DATA_ROOT", Path.home() / ".purity"))

    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_QSS)
    app.setQuitOnLastWindowClosed(False)

    existing_instance = _find_running_instance(data_root)
    if existing_instance is not None:
        if not _prompt_for_running_instance(existing_instance):
            return 0
        if not _restart_running_instance(existing_instance):
            _show_restart_failed(existing_instance["pid"])
            return 1

    runtime = create_purity_runtime(data_root)

    runtime.heartbeat.start()

    window = MainWindow(runtime=runtime)
    window.show()

    emit_app_started(
        runtime.journal,
        pid=runtime.session.pid,
        argv=list(sys.argv),
        data_root=str(data_root),
    )

    def _on_quit():
        emit_app_stopped(runtime.journal, reason="qt.shutdown")
        runtime.journal.close_sinks()
        runtime.tail.flush(reason="system.stop")
        runtime.heartbeat.stop()

    app.aboutToQuit.connect(_on_quit)

    # App-wide right-click → notes context menu
    notes_filter = NotesContextMenuFilter(app)
    app.installEventFilter(notes_filter)

    # Supervisor tray
    purity_tray = PurityTrayApp(data_root, main_window=window)
    purity_tray.start()
    window.attach_tray_app(purity_tray)
    purity_tray.notify_running(
        "Purity is running. If you close the main window it will stay active in the system tray.",
    )

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
