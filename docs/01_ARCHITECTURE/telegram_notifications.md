# Telegram Notifications — Purity App

## Overview

Purity uses the `shane_common.notify` notification layer with a `TelegramNotifyAdapter`
to push lifecycle alerts to a Telegram group. The integration is intentionally
transport-only: formatting is minimal and domain-specific logic stays inside Purity.

For the full notification system architecture (adapters, `NotifyManager`, idempotency,
anti-spam windowing, custom formatters) see:
[`shane_common/docs/notification_system.md`](../../../shane_common/docs/notification_system.md)

---

## Telegram Group

| Field    | Value              |
|----------|--------------------|
| Name     | Purity App Group   |
| Chat ID  | `-5102507990`      |
| Type     | group              |

The bot must be a member of this group with **Group Privacy disabled** (configured via
BotFather → Bot Settings → Group Privacy → Turn off). Remove and re-add the bot after
changing this setting.

---

## Bot Token

The bot token is **never stored in code or settings files**. It is read at runtime from
the environment variable:

```
PURITY_TELEGRAM_TOKEN=<token from BotFather>
```

Set this as a **User-scoped** Windows environment variable so it persists across reboots:

```powershell
[System.Environment]::SetEnvironmentVariable("PURITY_TELEGRAM_TOKEN", "<token>", "User")
```

Purity must be restarted after setting the variable for it to take effect.

---

## Chat ID Configuration

The chat ID is stored in Purity's settings file under the `app.telegram` category.
Configure it via **File → Preferences → app.telegram → telegram_chat_ids**.

Multiple chat IDs are supported as a comma-separated list:

```
-5102507990,-987654321
```

---

## Implementation Files

| File | Role |
|------|------|
| `services/telegram_notify.py` | `build_telegram_adapter_from_settings()` and `make_lifecycle_event()` helpers |
| `services/settings_schemas.py` | Registers `app.telegram` settings category with `telegram_chat_ids` definition |
| `app.py` | Sends `purity_app.shutdown` on clean quit |
| `supervisor.py` | Sends `purity_app.down` on crash detection; `purity_supervisor.shutdown` on supervisor exit |
| `ui/main_window.py` | Sidebar test buttons for manual verification |

---

## Lifecycle Events

| Event kind                  | Trigger                                              |
|-----------------------------|------------------------------------------------------|
| `purity_app.shutdown`       | Clean quit via `_on_quit()` in `app.py`              |
| `purity_app.down`           | Supervisor detects dead heartbeat (no restart yet)   |
| `purity_supervisor.shutdown`| Supervisor process is about to exit                  |

All events are sent at `WARNING` severity. The adapter filters to `{"WARNING", "URGENT"}`
by default (see `build_telegram_adapter` in `shane_common/notify/builder.py`).

---

## Test Buttons

Three buttons in the MainWindow sidebar allow manual end-to-end verification:

- **📨 TG: Shutdown** → sends `purity_app.shutdown` with `details=reason=test.button`
- **📨 TG: App Down** → sends `purity_app.down` with `details=reason=test.button`
- **📨 TG: Supervisor Down** → sends `purity_supervisor.shutdown` with `details=reason=test.button`

These buttons bypass the `NotifyManager` (no anti-spam windowing) and make a direct
HTTP call, surfacing any API errors in a dialog.

---

## Adding Further Bot Functionality

When extending the bot (e.g. inline keyboards, callback handlers, additional event
kinds), the recommended entry points are:

- **New event kinds**: add a `make_<x>_event()` helper in `services/telegram_notify.py`
  following the same pattern as `make_lifecycle_event()`.
- **Custom message formatting**: inject a `format_message` callable into
  `TelegramNotifyAdapter` — see the formatter pattern in `notification_system.md`.
- **Inline keyboards / callback handling**: inject `build_reply_markup` into
  `TelegramNotifyAdapter`. Handling callbacks requires a separate webhook or polling
  loop outside the current synchronous adapter design.
- **Additional chat targets**: add more IDs to `telegram_chat_ids` in Preferences
  (comma-separated). All IDs receive every notification.
