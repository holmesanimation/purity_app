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
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QMenu, QSystemTrayIcon

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


def main() -> int:
    args = _parse_args()
    data_root: Path = args.data_root
    heartbeats_dir = data_root / "_system" / "purity" / "heartbeats"

    purity_app_cmd: list[str] | None = None
    if args.purity_app_cmd:
        try:
            purity_app_cmd = json.loads(args.purity_app_cmd)
        except Exception:
            pass

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
    menu = QMenu()
    quit_action = menu.addAction("Quit Supervisor")
    tray.setContextMenu(menu)
    tray.show()

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
    _state: dict = {"dialog_active": False, "relaunch_grace_until": 0.0}

    # --- Poll callback --------------------------------------------------------
    def _poll() -> None:
        _, mtime, exit_present = reader.read("purity_app")

        # App is absent or dead (clean quit, task-kill, or crash — treat all the same).
        app_is_down = exit_present or mtime is None or reader.is_dead(mtime)

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

    # --- Graceful shutdown ---------------------------------------------------
    def _on_quit_action() -> None:
        app.quit()

    quit_action.triggered.connect(_on_quit_action)

    def _on_about_to_quit() -> None:
        heartbeat_writer.stop()

    app.aboutToQuit.connect(_on_about_to_quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
