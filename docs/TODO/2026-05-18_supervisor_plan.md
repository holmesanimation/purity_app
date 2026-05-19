# 2026-05-18 Plan: Purity Supervisor — Windows Startup + Auto-Restart

Add a separate headless supervisor process (`purity_supervisor.py`) that starts at Windows logon via the HKCU registry Run key. It uses the existing `ProcessLauncher` + `HeartbeatReader` + `AppendOnlyAuditLog` infrastructure from `shane_common.watchdog` to keep `app.py` alive and record liveness transitions to disk. `app.py` gains a `HeartbeatWriter` so the supervisor can detect its state.

## Context and Constraints

- Supervisor is a **separate headless process** — no GUI, no tray, no Qt dependency. It can only be stopped via Task Manager.
- The existing `PurityTrayApp` inside `app.py` remains the only tray icon; it is unaffected.
- Launch command for `app.py`: `python.exe app.py` from the repo root.
- Startup registration: **HKCU registry Run key** (user-scope, no elevation needed). The supervisor launches itself using `pythonw.exe` so no console window appears at logon.
- `app.py` currently writes **no heartbeat**. This must be added before the supervisor can detect liveness.
- A hard kill via Task Manager (`TerminateProcess`) is **undetectable by design** — the OS terminates the process without giving it any signal time. This is a known OS constraint, not a gap.
- All audit/heartbeat paths reuse the existing `PuritySupervisorClient` defaults under `~/.purity/_system/purity/`.

## Audit Findings

- `app.py` creates `PurityTrayApp(data_root)` which polls the heartbeat file and updates the tray icon colour. It does NOT write a heartbeat.
- `purity_app/services/supervisor_client.py` (`PuritySupervisorClient`) already wraps `HeartbeatReader` and `AppendOnlyAuditLog` with the correct paths. No changes needed there.
- `purity_app/gui/supervisor_tray.py` (`PurityTrayApp`) reads the heartbeat and drives tray icon colour. It does NOT restart the app. No changes needed there.
- `shane_common.watchdog.heartbeat_writer.HeartbeatWriter` — generic daemon thread, ready to use.
- `shane_common.watchdog.process_launcher.ProcessLauncher` + `ProcessLaunchConfig` — ready to use, has rate-limiting and cooldown built in.
- `shane_common.watchdog.heartbeat_reader.HeartbeatReader` — ready to use.
- `shane_common.watchdog.audit.AppendOnlyAuditLog` — ready to use.
- No `.bat` launchers, no `purity_supervisor.py`, no Windows startup registration exist yet.

## Phase 1 — Add HeartbeatWriter to app.py

Goal: `app.py` writes `purity_app.heartbeat.json` so the supervisor can detect its liveness.

1. Resolve `data_root` (same path already used for `PurityTrayApp`).
2. Instantiate `HeartbeatWriter(app_id="purity_app", heartbeats_dir=data_root / "_system/purity/heartbeats")`.
3. Call `writer.start()` after `QApplication` is created.
4. Wire `writer.stop()` to `QApplication.aboutToQuit` so the exit marker is written on clean shutdown.

Files: `purity_app/app.py`

## Phase 2 — Create purity_supervisor.py (headless poll loop)

Goal: a new script that monitors `app.py` liveness and restarts it when dead.

**Poll loop design:**
- Poll interval: 5 seconds.
- Liveness thresholds: `stale_s=10, dead_s=30` (faster than the HeartbeatReader default of 60 s).
- Derive liveness each tick: UNKNOWN → no heartbeat file, HEALTHY → fresh, STALE → slightly old, DEAD → old beyond dead_s threshold, EXPECTED_EXIT → exit marker present.
- On **HEALTHY/STALE/UNKNOWN → DEAD transition**: append audit record + call `launcher.maybe_restart()`.
- On **any → EXPECTED_EXIT transition**: append audit record + call `launcher.maybe_restart()` (supervisor's job is always-on; no "leave stopped" state in v1).
- On **DEAD/EXPECTED_EXIT → HEALTHY recovery**: append recovery audit record.
- On startup: if app is already HEALTHY, do NOT restart. Begin monitoring only.
- Rate limiting via `ProcessLaunchConfig(max_restarts_per_hour=6, cooldown_s=30)`.

**Shutdown recording:**
- Register `atexit` handler and `signal.SIGTERM` / `signal.SIGBREAK` (Windows) handlers to append `supervisor_shutdown` audit record before exit.
- Hard kill (`TerminateProcess`) cannot be caught — no record is written. This is expected.

**Audit events written:**

| Event | When |
|---|---|
| `supervisor_started` | Process boots |
| `app_liveness_transition` | Any prev → new state change |
| `app_restart_attempted` | `ProcessLauncher` fires |
| `supervisor_shutdown` | Clean exit only (atexit / signal) |

**No Qt dependency.** stdlib only + `shane_common.watchdog`. No tray, no window.

Files: New `purity_app/purity_supervisor.py`

## Phase 3 — Windows Startup Registration

Goal: supervisor registers itself in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` so it launches at logon.

CLI interface on the same `purity_supervisor.py`:
- `python purity_supervisor.py --register` — resolves the absolute path to `purity_supervisor.py` and writes the registry key. Value uses `pythonw.exe` (no console window at logon).
- `python purity_supervisor.py --unregister` — removes the registry key.
- No flag — runs the supervisor.

Registry details:
- Key: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
- Value name: `PuritySupervisor`
- Value data: `"<abs_path_to_pythonw.exe>" "<abs_path_to_purity_supervisor.py>"`
- Uses `winreg` (Python stdlib on Windows). No elevation required.

Files: `purity_app/purity_supervisor.py` (same file, CLI flag handling added in `main()`)

## Relevant Files

| File | Change |
|---|---|
| `purity_app/app.py` | Add `HeartbeatWriter` start/stop (Phase 1) |
| `purity_app/purity_supervisor.py` | New — headless supervisor + registry CLI (Phases 2 & 3) |
| `purity_app/services/supervisor_client.py` | Reuse for paths & audit log — no changes |
| `shane_common/watchdog/heartbeat_writer.py` | Reuse as-is |
| `shane_common/watchdog/heartbeat_reader.py` | Reuse as-is |
| `shane_common/watchdog/process_launcher.py` | Reuse as-is |
| `shane_common/watchdog/audit.py` | Reuse as-is |

## Verification Steps

1. `python purity_supervisor.py --register` → check key exists in `regedit` at `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\PuritySupervisor`.
2. Run `python purity_supervisor.py` in one terminal, `python app.py` in another → heartbeat file appears at `~/.purity/_system/purity/heartbeats/purity_app.heartbeat.json` within 2 s.
3. Kill `app.py` via Task Manager → within ~35 s supervisor appends DEAD transition + restart records to `purity.audit.jsonl`, and `app.py` relaunches.
4. Close `app.py` cleanly (window close / Alt+F4) → exit marker is written; supervisor appends EXPECTED_EXIT transition + restart record; `app.py` relaunches.
5. Kill supervisor via Task Manager → no audit record written (OS constraint, expected).
6. Ctrl+C supervisor (dev only) → `supervisor_shutdown` record appended.
7. `python purity_supervisor.py --unregister` → key removed from registry.
8. Reboot Windows → supervisor auto-starts at logon; `app.py` launches automatically.

## Explicit Out of Scope

- No graceful-stop IPC (e.g. named pipe "stop" command) — Task Manager kill only.
- No tray icon for the supervisor.
- No escalation notifications (push/email) on repeated restart failures.
- No supervisor-of-supervisor recursive watchdog.
- No "leave app stopped" intent mechanism — supervisor always restarts in v1.
