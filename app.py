# PySide6 UX Prototype â€” entry point
# Original app logic preserved in reminder_dialog.py, chrome_dialog.py,
# focus_guard.py, focus_guard_chrome_trigger.py (untouched).

import sys
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
from styles.theme import GLOBAL_QSS
from services.browser_session import BrowserSessionManager, ExtensionHeartbeatMonitor
from services.browser_session_api_server import BrowserSessionApiServer
from services.settings_schemas import build_purity_settings_manager, resolve_purity_data_root
from services.web_requests import submit_show_app_request
from shane_common.watchdog.heartbeat_reader import HeartbeatReader
from ui.main_window import (
    MainWindow,
    _append_startup_log,
    _launch_supervisor,
    _SUPERVISOR_STALE_S,
    _SUPERVISOR_DEAD_S,
)
from ui.notes_context_menu import NotesContextMenuFilter

# ---------------------------------------------------------------------------
# App-wide paths
# ---------------------------------------------------------------------------
DATA_ROOT = Path("G:/PURITY_APP")

# ---------------------------------------------------------------------------
# Singleton guard â€” Windows named mutex
# ---------------------------------------------------------------------------
_SINGLETON_MUTEX_NAME = "Local\\PurityApp_Singleton"
_singleton_mutex_handle = None  # set by _try_acquire_singleton_mutex, cleared in _on_quit


def _try_acquire_singleton_mutex() -> bool:
    """Try to acquire the named Windows mutex that marks this as the running instance.

    Returns True  -- we are the first/only instance (mutex freshly acquired).
    Returns False -- another instance already holds the mutex.
    Falls back to True on any error (fail-open) so startup is never blocked.
    """
    global _singleton_mutex_handle
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.CreateMutexW(None, 1, _SINGLETON_MUTEX_NAME)
        err = ctypes.get_last_error()
        if handle and err == 183:  # ERROR_ALREADY_EXISTS â€” another instance owns it
            kernel32.CloseHandle(handle)
            return False
        if handle:
            _singleton_mutex_handle = handle
            return True
        return True  # CreateMutexW returned NULL â€” unusual, fail open
    except Exception:
        return True  # fail open


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

    pid = heartbeat.get("pid") if isinstance(heartbeat, dict) else None
    if not _is_pid_running(pid):
        return None

    if client.heartbeat_reader.is_dead(mtime):
        return {"pid": int(pid), "state": "stale"}

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


def _is_supervisor_running(data_root: Path) -> bool:
    """Return True if purity_supervisor has a fresh heartbeat (not dead, no exit marker)."""
    heartbeats_dir = data_root / "_system" / "purity" / "heartbeats"
    reader = HeartbeatReader(
        heartbeats_dir=heartbeats_dir,
        stale_s=_SUPERVISOR_STALE_S,
        dead_s=_SUPERVISOR_DEAD_S,
    )
    _, mtime, exit_present = reader.read("purity_supervisor")
    return mtime is not None and not exit_present and not reader.is_dead(mtime)


# MainWindow lives in ui.main_window â€” imported above.
_MAIN_WINDOW_SENTINEL = None  # keep this line so diff tools show the seam


def main():
    from services.runtime import create_purity_runtime
    from services.journal_events import emit_app_started, emit_app_stopped
    from services.web_requests import start_purity_app
    from ui.system.supervisor_tray import PurityTrayApp

    settings_manager = build_purity_settings_manager()

    # Resolve data_root before QApplication so all paths are stable at startup.
    data_root = resolve_purity_data_root(settings_manager)

    _append_startup_log(data_root, f"Startup - executable={sys.executable!r}  argv={sys.argv!r}")

    # --- Singleton gate: named Windows mutex (checked before QApplication) ----
    if not _try_acquire_singleton_mutex():
        _append_startup_log(
            data_root,
            "Mutex gate: another instance already running - submitting show request and exiting.",
        )
        submit_show_app_request(data_root, source="app_launch")
        return 0

    _append_startup_log(data_root, "Mutex gate: acquired - proceeding with startup.")

    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_QSS)
    app.setQuitOnLastWindowClosed(False)

    existing_instance = _find_running_instance(data_root)
    if existing_instance is not None:
        submit_show_app_request(data_root, source="app_launch")
        return 0

    runtime = create_purity_runtime(data_root)
    browser_session_manager = BrowserSessionManager(data_root)
    browser_session_manager.clear_session()
    extension_heartbeat_monitor = ExtensionHeartbeatMonitor(data_root, stale_after_seconds=35.0)
    extension_heartbeat_monitor.clear()
    browser_session_api_server = BrowserSessionApiServer(
        browser_session_manager,
        extension_heartbeat_monitor,
    )
    browser_session_api_server.start()
    restart_requested = {"value": False}

    runtime.heartbeat.start()

    # --- Launch supervisor watchdog (separate process) -----------------------
    if not _is_supervisor_running(data_root):
        _launch_supervisor(data_root)
        _append_startup_log(data_root, "Supervisor watchdog launched.")
    else:
        _append_startup_log(data_root, "Supervisor watchdog already running â€” skipped launch.")

    window = MainWindow(
        runtime=runtime,
        settings_manager=settings_manager,
        browser_session_manager=browser_session_manager,
        extension_heartbeat_monitor=extension_heartbeat_monitor,
    )
    window.show()

    emit_app_started(
        runtime.journal,
        pid=runtime.session.pid,
        argv=list(sys.argv),
        data_root=str(data_root),
    )

    def _on_quit():
        global _singleton_mutex_handle
        browser_session_api_server.stop()
        browser_session_manager.clear_session()
        extension_heartbeat_monitor.clear()
        emit_app_stopped(runtime.journal, reason="qt.shutdown")
        runtime.journal.close_sinks()
        runtime.tail.flush(reason="system.stop")
        runtime.heartbeat.stop()
        if _singleton_mutex_handle is not None:
            try:
                import ctypes
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel32.CloseHandle(_singleton_mutex_handle)
            except Exception:
                pass
            _singleton_mutex_handle = None

    def _request_reload() -> None:
        restart_requested["value"] = True
        app.quit()

    def _maybe_restart() -> None:
        if restart_requested["value"]:
            start_purity_app(data_root)

    app.aboutToQuit.connect(_on_quit)
    app.aboutToQuit.connect(_maybe_restart)

    # App-wide right-click â†’ notes context menu
    notes_filter = NotesContextMenuFilter(app)
    app.installEventFilter(notes_filter)

    # Supervisor tray
    purity_tray = PurityTrayApp(
        data_root,
        main_window=window,
        reload_fn=_request_reload,
    )
    purity_tray.start()
    window.attach_tray_app(purity_tray)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
