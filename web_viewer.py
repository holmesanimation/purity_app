"""Purity Web Viewer — guarded Chrome launcher.

This is the entry point that replaces the Chrome desktop shortcut.
It checks that purity_app is running before submitting a web-launch
request.  If the app is not running, Chrome is blocked and the user
is told to open Purity first.

Architecture
------------
  Supervisor  ←──heartbeat──→  App  ←──heartbeat──→  (monitored)
                                ↑
                         required by
                                ↑
                          Web Viewer  (this file)

The Web Viewer has no direct relationship with the supervisor.
It only cares about the App mutex — if the App is not running,
browsing is blocked.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from services.web_requests import (  # noqa: E402
    append_web_request_log,
    resolve_data_root,
    start_purity_app,
    submit_web_launch_request,
)

_SINGLETON_MUTEX_NAME = "Local\\PurityApp_Singleton"
_APP_STARTUP_TIMEOUT_S = 30.0
_APP_STARTUP_POLL_S = 0.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_app_running() -> bool:
    """Return True iff purity_app is running (holds the singleton Windows mutex)."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenMutexW(0x00100000, False, _SINGLETON_MUTEX_NAME)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def _log(data_root: Path, message: str) -> None:
    pid = os.getpid()
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"{ts} [web_viewer PID={pid}] {message}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        log_path = data_root / "_system" / "purity" / "startup_debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _wait_for_app(timeout_s: float) -> bool:
    """Poll the mutex until the app acquires it or timeout expires. Returns True if ready."""
    import time
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _is_app_running():
            return True
        time.sleep(_APP_STARTUP_POLL_S)
    return False


def _show_start_failed_dialog() -> None:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication(sys.argv)
        dlg = QMessageBox()
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setWindowTitle("Purity Failed to Start")
        dlg.setText("Purity could not be started.")
        dlg.setInformativeText(
            f"Purity did not start within {int(_APP_STARTUP_TIMEOUT_S)} seconds. "
            "Please open it manually, then try again."
        )
        dlg.exec()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    data_root = resolve_data_root()
    _log(data_root, f"Web viewer fired — argv={sys.argv!r}")

    if not _is_app_running():
        _log(data_root, "App not running — launching purity_app and waiting for it to start.")
        append_web_request_log(
            data_root,
            "web_viewer.launching_app",
            "Web viewer is launching purity_app before submitting web request.",
            details={"argv": list(sys.argv)},
        )

        try:
            start_purity_app(data_root)
        except Exception as exc:
            _log(data_root, f"ERROR starting purity_app: {exc!r}")
            _show_start_failed_dialog()
            sys.exit(1)

        ready = _wait_for_app(_APP_STARTUP_TIMEOUT_S)

        if not ready:
            _log(data_root, f"App did not acquire mutex within {_APP_STARTUP_TIMEOUT_S}s — aborting.")
            append_web_request_log(
                data_root,
                "web_viewer.start_timeout",
                "Purity app did not start in time; web request aborted.",
                level="WARN",
                details={"argv": list(sys.argv), "timeout_s": _APP_STARTUP_TIMEOUT_S},
            )
            _show_start_failed_dialog()
            sys.exit(1)

        _log(data_root, "App is now running — submitting web launch request.")

    try:
        submit_web_launch_request(data_root, sys.argv[1:])
        _log(data_root, "Web launch request submitted.")
    except Exception as exc:
        _log(data_root, f"ERROR submitting web launch request: {exc!r}")
        append_web_request_log(
            data_root,
            "web_viewer.failed",
            "Web viewer failed to submit launch request.",
            level="ERROR",
            details={"argv": list(sys.argv)},
            exc=exc,
        )
        raise

    sys.exit(0)


if __name__ == "__main__":
    main()
