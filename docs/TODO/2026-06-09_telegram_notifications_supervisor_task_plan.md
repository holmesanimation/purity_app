# Plan: Telegram Notifications + Supervisor Windows Task

## Status
- DONE
- Completed: 2026-06-09

## Decisions
- Telegram events: app clean shutdown, app crash/killed (supervisor-detected), supervisor shutdown
- Telegram config stored in settings_schemas.py as new category "app.telegram"
- Remove "Quit Supervisor" tray button (task auto-restarts anyway)
- Panic notifications: out of scope for this task

---

## Phase 1: Settings — add Telegram category
**File**: `d:\code\git\purity_app\services\settings_schemas.py`
- Add `get_purity_telegram_category()` returning `SettingsCategory(category_id="app.telegram", ...)` with ONE SettingDefinition:
  - `telegram_chat_ids` (str, default="", label="Telegram Chat IDs", description="Comma-separated Telegram chat IDs (group or user). Token is read from PURITY_TELEGRAM_TOKEN env var.")
- In `build_purity_settings_manager()`: call `manager.register_category(get_purity_telegram_category())`

## Phase 2: Helper module
**New file**: `d:\code\git\purity_app\services\telegram_notify.py`
- `_TELEGRAM_CATEGORY = "app.telegram"`
- Token read via `os.environ.get("PURITY_TELEGRAM_TOKEN", "").strip()`
- `build_telegram_adapter_from_settings(settings_manager)` → INotifyAdapter
  - reads token from `PURITY_TELEGRAM_TOKEN` env var
  - reads chat_ids_str from settings
  - parses chat_ids as comma-separated ints
  - delegates to `shane_common.notify.builder.build_telegram_adapter(token, chat_ids, frozenset({"WARNING", "URGENT"}))` — returns NullNotifyAdapter automatically when token or chat_ids empty
- `make_lifecycle_event(kind, details=None)` → NotificationEvent(ts=time.time(), severity=WARNING, kind=kind, scope="global", details=details)

> **Pre-requisite (done):** `shane_common/notify/builder.py` — `build_telegram_adapter(token, chat_ids, alert_severities, ...)` factory added. Returns `NullNotifyAdapter` when token or chat_ids empty, else `TelegramNotifyAdapter`. Also simplifies `trading_platform/supervisor/alerting.py` — can replace its inline adapter construction with this factory.

## Phase 3: Wire app.py shutdown notification
**File**: `d:\code\git\purity_app\app.py`
- In `_on_quit()`: after `emit_app_stopped()`, call:
  ```python
  from services.telegram_notify import build_telegram_adapter_from_settings, make_lifecycle_event
  adapter = build_telegram_adapter_from_settings(settings_manager)
  adapter.send(make_lifecycle_event("purity_app.shutdown", details="reason=qt.shutdown"))
  ```
- `settings_manager` is already in scope (closure captures it from `main()`)

## Phase 4: Wire supervisor.py notifications
**File**: `d:\code\git\purity_app\supervisor.py`
- At top: add imports for settings + telegram_notify
- In `main()`, after arg parsing: call `build_purity_settings_manager()` and `build_telegram_adapter_from_settings(settings_manager)` → store as `telegram`
- In `_poll()` state dict: add `"app_was_up": True, "down_notified": False`
  - When `app_is_down` and `not _state["down_notified"]`: send `"purity_app.down"` event, set `_state["down_notified"] = True`
  - When app is healthy/stale (not down): reset `_state["down_notified"] = False`
- In `_on_about_to_quit()`: send `"purity_supervisor.shutdown"` event via telegram adapter

## Phase 5: Scheduled Task scripts
**New file**: `d:\code\git\purity_app\install_scheduled_task.py`
- Resolves pythonw.exe from sys.executable
- Resolves data_root via build_purity_settings_manager() + resolve_purity_data_root()
- Writes Task XML to temp file (UTF-16), calls `schtasks /Create /F /TN PuritySupervisor /XML ...`
- Includes purity_app_cmd arg pointing to current app.py
- Task settings: LogonTrigger, LeastPrivilege, RestartOnFailure PT30S/Count=99, ExecutionTimeLimit PT0S, IgnoreNew
- Deletes temp XML after install

**New file**: `d:\code\git\purity_app\uninstall_scheduled_task.py`
- Calls `schtasks /Delete /F /TN PuritySupervisor`

## Phase 6: Update _launch_supervisor() to prefer task
**File**: `d:\code\git\purity_app\ui\main_window.py`
- Try `subprocess.Popen(["schtasks", "/Run", "/TN", "PuritySupervisor"], creationflags=CREATE_NO_WINDOW)` first
- If that fails (task not installed), fall through to existing Popen logic

## Phase 7: Remove "Quit Supervisor" from tray
**File**: `d:\code\git\purity_app\supervisor.py`
- Remove `quit_action = menu.addAction("Quit Supervisor")`
- Remove `quit_action.triggered.connect(_on_quit_action)`
- Remove `def _on_quit_action()` function
- Keep `menu` for possible future use, or remove if empty

---

## Verification
1. Set bot_token + chat_ids in settings file; quit app → Telegram message received
2. Kill app via Task Manager → supervisor detects dead heartbeat → Telegram message received
3. Quit supervisor manually (via process kill) → Telegram message received
4. Run `install_scheduled_task.py` as admin → task appears in Task Scheduler
5. Reboot → supervisor starts automatically
6. `uninstall_scheduled_task.py` → task removed
7. _launch_supervisor logs show "Supervisor watchdog already running — skipped launch" after task install
