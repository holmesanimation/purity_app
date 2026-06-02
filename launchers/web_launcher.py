"""Standalone Chrome guard launcher.

Point your Chrome desktop shortcut here so every Chrome open goes through
the Purity guard popup first.  If approved, the real Chrome is launched.
If rejected, Chrome never starts.

NOTE: prefer web_viewer.py at the project root — it is the canonical entry
point and blocks Chrome when purity_app is not running.

Usage (via shortcut):
    pythonw web_viewer.py [chrome-args-or-url ...]
"""
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow running as a standalone script from any working directory.
_HERE = Path(__file__).parent.resolve()
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.web_requests import (  # noqa: E402
    append_web_request_log,
    resolve_data_root,
    start_purity_app,
    submit_web_launch_request,
)

_SINGLETON_MUTEX_NAME = "Local\\PurityApp_Singleton"


def _is_app_mutex_held() -> bool:
    """Return True iff the Purity app is currently running (holds the singleton mutex).

    Uses OpenMutexW — an OS-level probe that is unaffected by stale heartbeat
    files or PID reuse.  Falls back to False (assume not running) on any error
    so the caller always attempts to start the app.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        # SYNCHRONIZE (0x00100000) is the minimum right needed to open a mutex.
        handle = kernel32.OpenMutexW(0x00100000, False, _SINGLETON_MUTEX_NAME)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False  # fail open — assume not running, let app.py deduplicate


def _log_launcher(data_root: Path, message: str) -> None:
    """Write a launcher diagnostic line to startup_debug.log (captures pythonw.exe output)."""
    pid = os.getpid()
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"{ts} [web_launcher PID={pid}] {message}"
    try:
        log_path = Path(data_root) / "_system" / "purity" / "startup_debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def main() -> None:
    # Delegate to the canonical web_viewer entry point which enforces the
    # app-must-be-running dependency before submitting any web request.
    try:
        from web_viewer import main as _web_viewer_main
    except ModuleNotFoundError:
        from purity_app.web_viewer import main as _web_viewer_main  # type: ignore[no-redef]
    _web_viewer_main()


if __name__ == "__main__":
    main()

