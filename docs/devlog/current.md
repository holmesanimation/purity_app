# Current Development Log

Use this rolling file for recent completed work entries.

Entry template:

## YYYY-MM-DD - Short title

### Problem
...

### Cause
...

### Dead ends
...

### Solution
...

### Files touched
- path/to/file

### Verification
...

### Follow-ups
...

---

## 2026-06-09 - Initialize devlog workflow scaffold

### Problem
purity_app did not have a local devlog workflow scaffold aligned with the instructions contract.

### Cause
The repo had docs content but no dedicated docs/devlog structure with current log, fix index, and archive placeholder.

### Dead ends
none

### Solution
Created docs/devlog with current.md, fix_index.md, and archive/.gitkeep to mirror the existing workflow pattern used in the main project.

### Files touched
- docs/devlog/current.md
- docs/devlog/fix_index.md
- docs/devlog/archive/.gitkeep

---

## 2026-06-09 - Telegram notifications + supervisor scheduled task

### Problem
No alerting when the app crashed or was killed, and the supervisor did not auto-start on reboot.

### Cause
Feature not yet implemented — no Telegram integration, no Windows Scheduled Task wiring.

### Dead ends
none

### Solution
Added `services/telegram_notify.py` with `build_telegram_adapter_from_settings` and `make_lifecycle_event`. Registered `app.telegram` settings category (`telegram_chat_ids`) in `settings_schemas.py`. Wired shutdown notification into `app.py` `_on_quit()`. Wired crash detection and supervisor shutdown notifications into `supervisor.py`. Added `install_scheduled_task.py` and `uninstall_scheduled_task.py` for Windows Task Scheduler. Updated `ui/main_window.py` `_launch_supervisor` to prefer the scheduled task. Removed "Quit Supervisor" tray button. Added three Telegram test buttons to the MainWindow sidebar with direct HTTP diagnostics.

### Files touched
- services/telegram_notify.py
- services/settings_schemas.py
- app.py
- supervisor.py
- ui/main_window.py
- install_scheduled_task.py
- uninstall_scheduled_task.py

### Verification
Test buttons (📨 TG: Shutdown, 📨 TG: App Down, 📨 TG: Supervisor Down) in the sidebar successfully send messages to the Purity App Group Telegram group.

### Follow-ups
- Panic notifications (noted as out of scope for this task)

### Verification
Confirmed all three files were created and present under docs/devlog.

### Follow-ups
Start appending one completed-entry summary per finished fix and keep fix_index.md as a one-line lookup table.

---

## 2026-06-09 - WebPopup redesign: PanicReasonDialog-style vertical layout

### Problem
The permitted WebPopup used a legacy choice-button flow (Work / Research / Entertainment / Bored / Tempted) followed by a URL entry sub-dialog and a verse exercise sidecar. It collected no feelings, had no purpose gating, and did not align with the PanicReasonDialog visual language.

### Cause
The old design predated the PanicReasonDialog pattern and had grown stale as the intervention system evolved.

### Dead ends
none

### Solution
Replaced `ui/intervention/web_popup.py` entirely with a vertical PanicReasonDialog-inspired layout:
- Reminder/verse banner at top (title, optional note, bold ref + italic verse text)
- Full-width "How are you feeling?" reveal button, collapsed by default; 2-column feelings grid shown on click with `adjustSize()`
- "Why are you on the internet?" QTextEdit — commit gated on ≥ 4 words (`_is_proper_sentence`)
- "How long is this internet session?" duration combo (5m / 10m / 15m / 30m / 1h)
- "Start internet session" commit button — calls `accept()` after writing `selected_choice = "internet_session"`, `allowed_urls = []`, `reason_text`, `duration_seconds`, `selected_feelings`
- Removed `WebSessionConfigPopup`, `_CHOICES`, `is_permitted_web_choice`, verse exercise, and journal sidecar — all dead code after the redesign
- Blocked layout and MainWindow result contract preserved unchanged

### Files touched
- ui/intervention/web_popup.py
- tests/test_web_popup.py

### Verification
17/17 tests pass (`pytest tests/test_web_popup.py`). Syntax clean (`py_compile`). Manual runtime verification of Chrome watcher trigger and queued launcher flow pending.

### Follow-ups
- Manual smoke: open Chrome directly, confirm redesigned popup appears, commit, confirm browser session starts
- Manual smoke: queued launcher flow — confirm Commit returns Accepted and MainWindow launches Chrome

---

## 2026-06-10 - Left dock dashboard + VerseMemoryWidget

### Problem
No persistent side panel in the app for tools and quick-access content. The verse memorisation exercise in `WebPopup` was only accessible as a gate before a web session, not as a standalone practice tool.

### Cause
No dashboard component existed. Verse evaluation logic was tightly embedded in `WebPopup` with no reusable widget form.

### Dead ends
none

### Solution
- Created `ui/left_dock_dashboard.py` — a frameless `WindowStaysOnTopHint` tool window that docks to the left edge of the primary screen at full height. Collapses to a 2 px accent strip; expands to 1000 px via a `QPropertyAnimation` on a custom `content_width` property. A `_TabButton` child (20 px wide D-shape semicircle) sits at the right edge at all times and toggles open/close. Transparent corners achieved via `WA_TranslucentBackground` on both the window and the tab. A 1-second `QTimer` calls `raise_()` to re-assert topmost status. Open uses `OutExpo` (380 ms snap-then-ease); close uses `InExpo` (260 ms ease-then-snap).
- Created `ui/verse_memory_widget.py` — self-contained `VerseMemoryWidget` with verse header frame, practice `QTextEdit`, Hint (fade-out after 3 s) and Compare buttons, accuracy eval label, full verse comparison display, and a **New Verse** button. Evaluation logic (`_tokenize`, `_evaluate_verse`) lives here, keeping the widget fully self-contained.
- Dashboard hosts a `QScrollArea` content panel; `VerseMemoryWidget` added at the top with `addStretch()` below for future additions. Content panel hidden when collapsed to avoid input-stealing.
- `MainWindow.__init__` instantiates `LeftDockDashboard` and calls `show()` right after `_build_ui()`.

### Files touched
- ui/left_dock_dashboard.py (new)
- ui/verse_memory_widget.py (new)
- ui/main_window.py

### Verification
- Launch app — 2 px green strip visible on left edge of primary monitor
- Click tab — panel snaps open then eases into final position; verse widget visible at top
- Click tab again — panel eases out then snaps shut to strip
- Type verse from memory, press Enter or tab away — accuracy % appears
- Click Hint — two words flash and fade; clicking again advances the word window
- Click Compare — full verse displayed with missed words underlined
- Click New Verse — new verse loaded, all state reset
- Other app windows do not cover the dashboard strip

### Follow-ups
- Add more content sections below the verse widget (goals, streak, pulse quick-launch)
- Persist last-used verse key across app restarts

---
