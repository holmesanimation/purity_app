"""File-backed handoff for guarded web-launch requests.

The standalone launcher does not own a Purity runtime. It writes a request file
and lets the running app process the dialog, journaling, and browser launch
under the app's active run_id.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from shane_common.io.atomic import write_json_atomic, write_text_atomic

from services.supervisor_client import PuritySupervisorClient


APP_ID = "purity_app"
APPROVED_MARKER = Path(tempfile.gettempdir()) / "purity_web_approved"
REQUEST_SCHEMA_VERSION = 1


def resolve_data_root() -> Path:
    return Path(os.environ.get("PURITY_DATA_ROOT", Path.home() / ".purity"))


def request_inbox_dir(data_root: Path) -> Path:
    return Path(data_root) / "_system" / "purity" / "web_requests" / "inbox"


def web_requests_log_path(data_root: Path) -> Path:
    return Path(data_root) / "_system" / "purity" / "web_requests" / "web_requests.log.jsonl"


def app_stdout_log_path(data_root: Path) -> Path:
    return Path(data_root) / "_system" / "purity" / "web_requests" / "app_stdout.log"


def app_stderr_log_path(data_root: Path) -> Path:
    return Path(data_root) / "_system" / "purity" / "web_requests" / "app_stderr.log"


def append_web_request_log(
    data_root: Path,
    event: str,
    message: str = "",
    *,
    level: str = "INFO",
    details: dict[str, Any] | None = None,
    exc: BaseException | None = None,
) -> None:
    path = web_requests_log_path(data_root)
    row: dict[str, Any] = {
        "ts": time.time(),
        "level": str(level),
        "event": str(event),
        "message": str(message),
        "details": dict(details or {}),
    }
    if exc is not None:
        row["exception"] = repr(exc)
        row["traceback"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception:
        traceback.print_exc()


def submit_web_launch_request(data_root: Path, args: list[str]) -> Path:
    request_id = uuid.uuid4().hex
    path = request_inbox_dir(data_root) / f"{int(time.time() * 1000)}_{request_id}.json"
    write_json_atomic(
        path,
        {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "request_id": request_id,
            "created_ts": time.time(),
            "args": list(args),
        },
        sort_keys=False,
    )
    append_web_request_log(
        data_root,
        "request.submitted",
        "Queued guarded web launch request.",
        details={"path": str(path), "args": list(args)},
    )
    return path


def read_pending_web_launch_requests(data_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    inbox = request_inbox_dir(data_root)
    if not inbox.is_dir():
        return []

    pending: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(inbox.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            append_web_request_log(
                data_root,
                "request.read_failed",
                "Could not read pending web launch request.",
                level="ERROR",
                details={"path": str(path)},
                exc=exc,
            )
            continue
        if isinstance(data, dict):
            pending.append((path, data))
        else:
            append_web_request_log(
                data_root,
                "request.invalid_payload",
                "Pending web launch request was not a JSON object.",
                level="ERROR",
                details={"path": str(path), "payload_type": type(data).__name__},
            )
    return pending


def mark_web_launch_request_done(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        append_web_request_log(
            path.parents[4] if len(path.parents) > 4 else resolve_data_root(),
            "request.delete_failed",
            "Could not delete processed web launch request.",
            level="ERROR",
            details={"path": str(path)},
            exc=exc,
        )


def write_launcher_approved_marker() -> None:
    write_text_atomic(APPROVED_MARKER, str(time.time()))


def is_purity_app_running(data_root: Path) -> bool:
    try:
        client = PuritySupervisorClient(data_root)
        heartbeat, mtime, exit_present = client.heartbeat_reader.read(APP_ID)
    except Exception as exc:
        append_web_request_log(
            data_root,
            "running_check.failed",
            "Could not check whether Purity is running.",
            level="ERROR",
            exc=exc,
        )
        return False

    if heartbeat is None or mtime is None:
        append_web_request_log(
            data_root,
            "running_check.not_running",
            "No active Purity heartbeat found.",
            details={"heartbeat_present": heartbeat is not None, "exit_marker_present": exit_present},
        )
        return False
    if client.heartbeat_reader.is_dead(mtime):
        append_web_request_log(
            data_root,
            "running_check.dead_heartbeat",
            "Purity heartbeat is dead.",
            details={"mtime": mtime},
        )
        return False

    pid = heartbeat.get("pid") if isinstance(heartbeat, dict) else getattr(heartbeat, "pid", None)
    running = _is_pid_running(pid)
    if exit_present and running:
        try:
            exit_marker = client.heartbeats_dir / f"{APP_ID}.exit_marker.json"
            if exit_marker.exists() and exit_marker.stat().st_mtime > mtime:
                append_web_request_log(
                    data_root,
                    "running_check.exit_after_heartbeat",
                    "Exit marker is newer than heartbeat, treating app as not running.",
                    details={"pid": pid, "mtime": mtime, "exit_marker": str(exit_marker)},
                )
                return False
        except OSError as exc:
            append_web_request_log(
                data_root,
                "running_check.exit_marker_stat_failed",
                "Could not inspect exit marker timestamp.",
                level="ERROR",
                details={"pid": pid},
                exc=exc,
            )
            return False

    append_web_request_log(
        data_root,
        "running_check.result",
        "Checked Purity process liveness.",
        details={"pid": pid, "running": running, "exit_marker_present": exit_present},
    )
    return running


def start_purity_app(data_root: Path | None = None) -> None:
    data_root = Path(data_root) if data_root is not None else resolve_data_root()
    app_path = Path(__file__).resolve().parent.parent / "app.py"
    pythonw = Path(sys_executable()).with_name("pythonw.exe")
    executable = str(pythonw if pythonw.exists() else Path(sys_executable()))
    env = dict(os.environ)
    env["PURITY_DATA_ROOT"] = str(data_root)
    app_stdout_log_path(data_root).parent.mkdir(parents=True, exist_ok=True)
    stdout_fh = open(app_stdout_log_path(data_root), "a", encoding="utf-8")
    stderr_fh = open(app_stderr_log_path(data_root), "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [executable, str(app_path)],
            cwd=str(app_path.parent),
            stdout=stdout_fh,
            stderr=stderr_fh,
            env=env,
        )
        append_web_request_log(
            data_root,
            "app.start_requested",
            "Started Purity app for queued web launch request.",
            details={"pid": proc.pid, "executable": executable, "app_path": str(app_path)},
        )
    except Exception as exc:
        append_web_request_log(
            data_root,
            "app.start_failed",
            "Could not start Purity app for queued web launch request.",
            level="ERROR",
            details={"executable": executable, "app_path": str(app_path)},
            exc=exc,
        )
        raise
    finally:
        stdout_fh.close()
        stderr_fh.close()


def sys_executable() -> str:
    import sys

    return sys.executable


def _is_pid_running(pid: object) -> bool:
    try:
        actual_pid = int(pid)
    except (TypeError, ValueError):
        return False

    if actual_pid <= 0:
        return False

    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {actual_pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                creationflags=creationflags,
                timeout=5,
            )
        except Exception as exc:
            append_web_request_log(
                resolve_data_root(),
                "pid_check.failed",
                "Could not query PID with tasklist.",
                level="ERROR",
                details={"pid": actual_pid},
                exc=exc,
            )
            return False

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("INFO:"):
                continue
            parts = [part.strip('"') for part in line.split('\",\"')]
            if len(parts) >= 2:
                try:
                    return int(parts[1]) == actual_pid
                except ValueError:
                    continue
        return False

    try:
        os.kill(actual_pid, 0)
    except OSError:
        return False
    return True