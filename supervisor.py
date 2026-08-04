"""Purity Supervisor — standalone watchdog process.

Launched by purity_app at startup. Monitors purity_app's heartbeat and shows
a dialog if the app is unresponsive (no exit marker present).

CLI args
--------
--data-root PATH          Required.  Root data directory for purity_app.
--purity-app-cmd JSON     Optional.  JSON-encoded list: command to relaunch
                          purity_app (e.g. '["pythonw.exe", "app.py"]').

Exit behaviour
--------------
- Exits cleanly when purity_app writes an exit marker (graceful shutdown).
- Keeps running if purity_app is absent/dead; shows a dialog instead.
"""
from __future__ import annotations

import argparse
import json
import traceback
import os
import signal
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from shane_common.watchdog.heartbeat_reader import HeartbeatReader
from shane_common.watchdog.heartbeat_writer import HeartbeatWriter
from shane_common.watchdog.process_launcher import ProcessLauncher, ProcessLaunchConfig
from shane_common.watchdog.tray.icons import (
    COLOR_GRAY,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    make_circle_icon,
)
from services.settings_schemas import build_purity_settings_manager
from services.telegram_notify import (
    build_telegram_adapter_from_settings,
    make_lifecycle_event,
)

_SUPERVISOR_APP_ID = "purity_supervisor"
_POLL_INTERVAL_MS = 5_000
_STALE_S = 15.0
_DEAD_S = 30.0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Purity Supervisor Watchdog")
    p.add_argument("--data-root", required=True, type=Path, metavar="PATH")
    p.add_argument(
        "--purity-app-cmd",
        type=str,
        default=None,
        metavar="JSON",
        help="JSON-encoded list: command to relaunch purity_app",
    )
    return p.parse_args()


import socket as _socket

_SINGLETON_PORT = 47823  # Fixed port for PuritySupervisor singleton guard


def _acquire_singleton_mutex() -> object | None:
    """Bind to a fixed loopback port as a singleton guard. Returns socket on success, None if already running."""
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 0)
        s.bind(("127.0.0.1", _SINGLETON_PORT))
        return s  # Keep bound; released automatically when process exits
    except OSError:
        return None


def _get_parent_info() -> str:
    try:
        ppid = os.getppid()
        import ctypes, ctypes.wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, ppid)
        if not h:
            return f"ppid={ppid}"
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.wintypes.DWORD(260)
        ctypes.WinDLL("kernel32").QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        kernel32.CloseHandle(h)
        name = Path(buf.value).name if buf.value else "unknown"
        return f"ppid={ppid} parent={name}"
    except Exception:
        return "ppid=unknown"


def _send_telegram_notification(data_root: Path, settings_manager, kind: str, details: str) -> None:
    import urllib.parse, urllib.request
    token = os.environ.get("PURITY_TELEGRAM_TOKEN", "").strip()
    chat_ids_str = str(settings_manager.get("app.telegram", "telegram_chat_ids") or "")
    chat_ids = [c.strip() for c in chat_ids_str.split(",") if c.strip()]
    if not token or not chat_ids:
        _log_supervisor(data_root, f"Telegram not configured: token_present={bool(token)} chat_ids={chat_ids_str!r}")
        return
    text = f"[WARNING] {kind}\nscope=global\ndetails={details}"
    for chat_id in chat_ids:
        try:
            params = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=params, method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode()
            _log_supervisor(data_root, f"Telegram ok: chat_id={chat_id} response={body[:80]}")
        except Exception as exc:
            _log_supervisor(data_root, f"Telegram FAILED: chat_id={chat_id} error={exc}")


def _log_supervisor(data_root: Path, message: str) -> None:
    import datetime
    parent_info = _get_parent_info()
    line = f"[PuritySupervisor] {datetime.datetime.now().isoformat(timespec='seconds')} [PID={os.getpid()} {parent_info}] {message}"
    print(line, flush=True)
    try:
        log_path = data_root / "_system" / "purity" / "supervisor_debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def main() -> int:
    _mutex = _acquire_singleton_mutex()
    if _mutex is None:
        print(f"[PuritySupervisor] PID={os.getpid()} {_get_parent_info()} Already running (port busy) — exiting.", flush=True)
        return 0

    args = _parse_args()
    _log_supervisor(args.data_root, "Startup — singleton port acquired.")
    settings_manager = build_purity_settings_manager()
    telegram = build_telegram_adapter_from_settings(settings_manager)
    data_root: Path = args.data_root
    heartbeats_dir = data_root / "_system" / "purity" / "heartbeats"

    purity_app_cmd: list[str] | None = None
    if args.purity_app_cmd:
        try:
            purity_app_cmd = json.loads(args.purity_app_cmd)
        except Exception:
            traceback.print_exc()

    # --- Own heartbeat (daemon thread, clears exit marker on start) ----------
    heartbeat_writer = HeartbeatWriter(
        app_id=_SUPERVISOR_APP_ID,
        heartbeats_dir=heartbeats_dir,
    )
    heartbeat_writer.start()

    # --- Qt application (no main window; dialogs and tray only) --------------
    app: QApplication = QApplication.instance() or QApplication(sys.argv)  # type: ignore[assignment]
    app.setQuitOnLastWindowClosed(False)

    # --- Tray icon ------------------------------------------------------------
    tray = QSystemTrayIcon()
    tray.setIcon(make_circle_icon(COLOR_GRAY))
    tray.setToolTip("Purity Supervisor")
    tray.show()

    tray_menu = QMenu()
    quit_action = tray_menu.addAction("Quit Supervisor")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(tray_menu)

    # --- Heartbeat reader for purity_app -------------------------------------
    reader = HeartbeatReader(
        heartbeats_dir=heartbeats_dir,
        stale_s=_STALE_S,
        dead_s=_DEAD_S,
    )

    # --- Optional relaunch infrastructure ------------------------------------
    launcher: ProcessLauncher | None = None
    launch_cfg: ProcessLaunchConfig | None = None
    if purity_app_cmd:
        launcher = ProcessLauncher()
        launch_cfg = ProcessLaunchConfig(
            app_id="purity_app",
            launch_cmd=purity_app_cmd,
            max_restarts_per_hour=3,
            cooldown_s=30.0,
        )

    # dialog_active: blocks a second dialog while one is open
    # relaunch_grace_until: monotonic deadline after a relaunch; skip alerts until then
    _state: dict = {
        "dialog_active": False,
        "relaunch_grace_until": 0.0,
        "app_was_up": False,
        "down_notified": True,  # suppress notification until app has been seen healthy at least once
    }

    # --- Poll callback --------------------------------------------------------
    def _poll() -> None:
        _, mtime, exit_present = reader.read("purity_app")

        # App is absent or dead (clean quit, task-kill, or crash — treat all the same).
        app_is_down = exit_present or mtime is None or reader.is_dead(mtime)

        if app_is_down:
            if _state["app_was_up"] and not _state["down_notified"]:
                _log_supervisor(data_root, "Sending purity_app.down notification.")
                _send_telegram_notification(data_root, settings_manager, "purity_app.down", "reason=heartbeat.down")
                _state["down_notified"] = True
            _state["app_was_up"] = False
        else:
            _state["app_was_up"] = True
            _state["down_notified"] = False

        if app_is_down:
            # Suppress alert while a recent relaunch is still starting up.
            if time.monotonic() < _state["relaunch_grace_until"]:
                tray.setIcon(make_circle_icon(COLOR_YELLOW))
                tray.setToolTip("Purity Supervisor — App starting…")
                return

            tray.setIcon(make_circle_icon(COLOR_RED))
            tray.setToolTip("Purity Supervisor — App DOWN")

            if not _state["dialog_active"]:
                _state["dialog_active"] = True
                dlg = QMessageBox()
                dlg.setIcon(QMessageBox.Icon.Critical)
                dlg.setWindowTitle("Purity App Down")
                dlg.setText("The Purity App is not running.")
                dlg.setInformativeText(
                    "The Purity App has exited or stopped responding. "
                    "It must be running to enforce content restrictions."
                )
                if launch_cfg is not None:
                    relaunch_btn = dlg.addButton(
                        "Relaunch App", QMessageBox.ButtonRole.AcceptRole
                    )
                    dlg.addButton("OK", QMessageBox.ButtonRole.RejectRole)
                else:
                    relaunch_btn = None
                    dlg.addButton(QMessageBox.StandardButton.Ok)

                dlg.exec()
                _state["dialog_active"] = False

                if (
                    relaunch_btn is not None
                    and dlg.clickedButton() is relaunch_btn
                    and launcher is not None
                    and launch_cfg is not None
                ):
                    launcher.maybe_restart(launch_cfg)
                    # Give the app time to start and write its first heartbeat.
                    _state["relaunch_grace_until"] = time.monotonic() + 30.0

        elif mtime is not None and reader.is_stale(mtime):
            tray.setIcon(make_circle_icon(COLOR_YELLOW))
            tray.setToolTip("Purity Supervisor — App STALE")
        else:
            tray.setIcon(make_circle_icon(COLOR_GREEN))
            tray.setToolTip("Purity Supervisor — App healthy")

    poll_timer = QTimer()
    poll_timer.setInterval(_POLL_INTERVAL_MS)
    poll_timer.timeout.connect(_poll)
    poll_timer.start()
    QTimer.singleShot(0, _poll)

    def _on_about_to_quit() -> None:
        _send_telegram_notification(data_root, settings_manager, "purity_supervisor.shutdown", "reason=qt.shutdown")
        heartbeat_writer.stop()

    app.aboutToQuit.connect(_on_about_to_quit)

    # SIGTERM handler — fires app.quit() so aboutToQuit is emitted before exit.
    # On Windows, taskkill /PID (without /F) sends SIGTERM to the process.
    def _on_sigterm(signum, frame):
        app.quit()

    signal.signal(signal.SIGTERM, _on_sigterm)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
