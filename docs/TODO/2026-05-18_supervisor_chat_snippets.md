# 2026-05-18 Chat Snippets: Purity Supervisor — Windows Startup + Auto-Restart

Minimum recommended chats: 2.

Why 2 chats:
- Chat 1 covers the smallest behavioural change: adding `HeartbeatWriter` to `app.py` so the app starts writing liveness to disk. This is isolated, safe to validate immediately, and unblocks Chat 2.
- Chat 2 implements the headless supervisor script and the Windows startup registration in one pass. These belong together because the supervisor is useless without its startup hook, and both are pure additions (new file + registry write) with no risk to existing app behaviour.

## Chat 1 — Add HeartbeatWriter to app.py

Paste this into a new chat:

```text
Implement only Phase 1 from [docs/TODO/2026-05-18_supervisor_plan.md](docs/TODO/2026-05-18_supervisor_plan.md).

Context:
- `app.py` currently creates a `PurityTrayApp` which reads the heartbeat file. It does NOT write one.
- `shane_common.watchdog.heartbeat_writer.HeartbeatWriter` is ready to use — no changes needed in shane_common.
- `purity_app/services/supervisor_client.py` (`PuritySupervisorClient`) already exposes `heartbeats_dir` with the correct path. Use that rather than constructing the path manually.

Constraints:
- Only touch `app.py`. Do not create any new files.
- Do not modify supervisor_tray.py, supervisor_client.py, or any shane_common files.
- The HeartbeatWriter must be started after QApplication is created and stopped (with exit marker) via QApplication.aboutToQuit.
- data_root is already resolved near the bottom of main() — reuse that variable.

Validation:
- Run `python app.py` and confirm `~/.purity/_system/purity/heartbeats/purity_app.heartbeat.json` is created and its mtime updates every 2 s.
- Confirm `purity_app.exit_marker.json` appears in the same directory when the app is closed cleanly.

Deliverables:
- Single focused diff to app.py.
- Validation result confirming the heartbeat file appears and updates.
```

## Chat 2 — Headless supervisor process + Windows startup registration

Paste this into a new chat after Chat 1 is complete:

```text
Implement Phases 2 and 3 from [docs/TODO/2026-05-18_supervisor_plan.md](docs/TODO/2026-05-18_supervisor_plan.md).

Context:
- Chat 1 already added HeartbeatWriter to app.py. purity_app now writes purity_app.heartbeat.json.
- All watchdog infrastructure (HeartbeatReader, ProcessLauncher, AppendOnlyAuditLog) is ready in shane_common.watchdog.
- PuritySupervisorClient in purity_app/services/supervisor_client.py exposes heartbeat_reader, audit_log, and heartbeats_dir. Use it for all path and reader access.
- The supervisor must NOT import Qt or PySide6.

Constraints:
- Create one new file: purity_app/purity_supervisor.py.
- Do not modify any existing file except to add the CLI entry if needed.
- The supervisor must be a plain blocking poll loop (no Qt event loop) so it can be terminated only via Task Manager.
- Liveness thresholds: stale_s=10, dead_s=30.
- Poll interval: 5 seconds.
- Derive a simple liveness string each tick: UNKNOWN, HEALTHY, STALE, DEAD, EXPECTED_EXIT.
- Only act on state transitions (prev != current). Do not fire audit records or restart attempts on every tick.
- On startup with a HEALTHY app: begin monitoring, do NOT restart.
- Use ProcessLaunchConfig(app_id="purity_app", launch_cmd=["python.exe", "app.py"], max_restarts_per_hour=6, cooldown_s=30). The launch_cmd must be run from the repo root directory — resolve that path relative to purity_supervisor.py's own __file__ location.
- atexit and signal handlers (SIGTERM, SIGBREAK on Windows) must append a supervisor_shutdown audit record on clean exit.
- Hard kill via Task Manager is undetectable — no special handling required for that case.
- --register writes HKCU\Software\Microsoft\Windows\CurrentVersion\Run\PuritySupervisor using pythonw.exe (no console window). Resolve the absolute path to both pythonw.exe (via sys.executable sibling) and purity_supervisor.py at registration time.
- --unregister removes the registry key.
- No flag = run the supervisor.

Validation:
- Run python purity_supervisor.py in one terminal, python app.py in another. Confirm heartbeat is read as HEALTHY and no restart is attempted.
- Kill app.py via Task Manager. Confirm within ~35 s the audit log shows a DEAD transition and restart attempt, and app.py relaunches.
- Close app.py cleanly. Confirm exit marker is detected, EXPECTED_EXIT transition is recorded, and app.py relaunches.
- Run python purity_supervisor.py --register and verify the registry key in regedit.
- Run python purity_supervisor.py --unregister and verify the key is removed.
- Ctrl+C the supervisor and confirm a supervisor_shutdown record appears in purity.audit.jsonl.

Deliverables:
- purity_app/purity_supervisor.py (new file).
- Validation results for each step above.
- Short note on anything deferred or out of scope.
```

## Deferred future chats

Do not start these until there is real demand:
- Graceful-stop IPC (named pipe or file-based "stop intent") so the supervisor can be instructed to leave the app stopped without a Task Manager kill.
- Escalation notifications (push/email) after N consecutive restart failures.
- Supervisor tray icon (would move it out of app.py and into a combined supervisor+tray process).
- Supervisor-of-supervisor recursive watchdog.
