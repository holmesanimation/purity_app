# 2026-05-27 Chat Snippets: Panic Button Implementation

> **Status: COMPLETE** — All 5 chats implemented. 188/188 tests passing as of 2026-05-27.

Minimum recommended chats: 5.

- **Chat 1** — Domain model, state machine, journal taxonomy, settings. Pure Python, no Qt. Fully testable in isolation.
- **Chat 2** — Browser session override counters, elevated state polling in MainWindow, panic_stats aggregate store.
- **Chat 3** — Persistent panic button widget + MainWindow immediate interruption handler.
- **Chat 4** — Reason selection dialog + intervention workspace (reorientation panels, progress, countdown).
- **Chat 5** — Wire together: emit outcomes on close, connect log viewer, verify disk journal, tone pass.

---

## Chat 1 — Domain model, state machine, journal taxonomy

Paste into a new chat:

```text
Implement Phase 0 and Phase 1 (settings + panic_stats only) from docs/TODO/2026-05-27_panic_button_plan.md.

No Qt. No browser process code. Pure Python service layer only.

What to create:
- purity_app/services/panic_session.py
  - PanicSessionState enum: INTERRUPTING, SELECTING_REASONS, REFLECTION, REORIENTATION, COUNTDOWN, POST_RECOVERY, CLOSED
  - PanicSessionOutcome enum: RECOVERED, ESCALATED, ABANDONED, INTERRUPTED
  - PanicSession class with panic_session_id (uuid4), selected_reason_ids, reflections (dict keyed by reason_id), reoriented_reason_ids (set), countdown_started, notify_stub_clicked, started_while_elevated, state, outcome
  - Guarded transition methods: start_interrupting(), start_reason_selection(), start_reflection(), reorient_topic(reason_id, reflection_text), start_countdown(), complete_countdown(), close(outcome). Each must raise ValueError if called from an illegal state.

- purity_app/services/panic_stats.py
  - PanicStats class persisting to <data_root>/data/panic/reason_counts.json
  - Schema: {reason_id: {count: int, last_seen_ts: float}}
  - Methods: record_reasons(reason_ids: list[str]) increments counts and last_seen_ts; get_top_reasons(n: int) returns list of reason_ids sorted by count descending; load/save via atomic write (use shane_common.io.atomic.write_json_atomic).
  - Never stores reflection text.

- Update purity_app/services/journaling_profile.py
  - Add panic kind constants: panic.started, panic.state_changed, panic.reasons_selected, panic.reflection_saved, panic.topic_acknowledged, panic.countdown_started, panic.countdown_completed, panic.closed, panic.notify_group_clicked, panic.danger_elevated, panic.danger_cleared
  - Add all to _PURITY_KINDS frozenset
  - Route panic.* events to journals/<date>/panic.jsonl (stream name "panic")

- Update purity_app/services/journal_events.py (or add panic_events.py)
  - Emitters for all panic kinds above
  - Every emitter accepts panic_session_id; include it in payload and in correlation={panic_session_id: ...}

- Update purity_app/services/log_kind_map.py
  - Add KindSpec for each panic kind with appropriate severity and message templates
  - Classify all panic.* as TYPE_INTERVENTION in classify_purity_row_type

- Update purity_app/services/settings_schemas.py
  - Add panic_cooldown_seconds (int, default 300) and panic_auto_accountability_enabled (bool, default True) to the general category

Tests to add:
- purity_app/tests/test_panic_session.py — legal transitions, duplicate countdown prevention, reorientation after CLOSED rejected, started_while_elevated persisted, outcome assignment
- purity_app/tests/test_panic_stats.py — counts increment, persist, reload, top reasons order, reflection text never present
- Extend purity_app/tests/test_purity_journal_events.py with panic emitter tests (panic.started payload has panic_session_id and started_while_elevated; panic.closed payload has outcome)

Validation:
- pytest purity_app/tests/test_panic_session.py purity_app/tests/test_panic_stats.py purity_app/tests/test_purity_journal_events.py
- Confirm panic.* events route to panic.jsonl and appear as Intervention rows when replayed in the log viewer.
```

---

## Chat 2 — Browser override counters and elevated state

Paste into a new chat after Chat 1:

```text
Implement the browser override signal and MainWindow elevated state polling from Phase 1 of docs/TODO/2026-05-27_panic_button_plan.md.

Context: Chat 1 already added panic_session.py, panic_stats.py, panic event kinds, and settings. Read those files before writing.

What to change:
- purity_app/services/browser_session.py: BrowserSessionManager.allow_url()
  - After updating allowed_urls/allowed_domains, also write override_count (incremented), last_override_ts (current time.time()), last_override_url (the newly allowed URL) into the active session payload.
  - The increment must be atomic with the rest of the allow_url write (same locked write).

- purity_app/app.py: MainWindow
  - Add _panic_elevated: bool = False
  - Add _panic_last_override_count: int = 0
  - In _process_web_launch_requests (or add a dedicated _poll_panic_elevation timer at the same 500ms cadence):
    - Read active session payload from _browser_session_manager
    - If override_count > _panic_last_override_count: set _panic_elevated = True, update counter, emit panic.danger_elevated (if runtime is not None)
    - If session is no longer active and _panic_elevated is True: set _panic_elevated = False, emit panic.danger_cleared
  - Wire _panic_elevated into panic button set_elevated() once the button exists (stub the call for now with a comment)

Tests to add:
- Extend purity_app/tests/test_browser_session.py:
  - allow_url() increments override_count from 0 to 1 on first override
  - allow_url() records last_override_url and last_override_ts
  - override_count does not appear when session is inactive (clear_session resets)

Validation:
- pytest purity_app/tests/test_browser_session.py
```

---

## Chat 3 — Persistent panic button + immediate interruption handler

Paste into a new chat after Chat 2:

```text
Implement Phase 2 and Phase 3 from docs/TODO/2026-05-27_panic_button_plan.md.

Context: Chats 1–2 added panic domain model, journal kinds, stats, and browser override counters. Read app.py, browser_session.py, and web_timer_pill.py before writing.

What to create:
- purity_app/ui/intervention/panic_button.py
  - Small frameless, always-on-top QWidget, fixed size (~72×40), bottom-right of primaryScreen().availableGeometry()
  - Semi-transparent (opacity ~0.55) by default, fully opaque on hover (enterEvent/leaveEvent)
  - Contains one QPushButton with label "🆘 Help" or similar short label
  - Signal: panic_requested (no payload)
  - Method: set_elevated(bool) — changes button background/border to a danger accent when elevated
  - WindowStaysOnTopHint | FramelessWindowHint | Tool

What to change:
- purity_app/app.py: MainWindow
  - Instantiate PanicButton after _web_timer_pill setup; store as _panic_btn
  - Connect _panic_btn.panic_requested to _start_panic_intervention
  - In _poll_panic_elevation: call _panic_btn.set_elevated(_panic_elevated)
  - Add _active_panic_session: PanicSession | None = None
  - Add _active_panic_window: QWidget | None = None
  - Add _start_panic_intervention():
    1. If _active_panic_session is not None and window still visible: raise window, return
    2. Create PanicSession, call start_interrupting()
    3. Capture started_while_elevated from _panic_elevated
    4. Call session.set_started_while_elevated(started_while_elevated) or equivalent
    5. taskkill_processes(list(_WATCHED_BROWSERS))
    6. _web_timer_pill.stop_session()
    7. _browser_session_manager.clear_session()
    8. Clear _web_session_* fields
    9. Emit panic.started via runtime.journal (if runtime is not None)
    10. session.start_reason_selection()
    11. Open PanicReasonDialog (stub import — dialog does not exist yet; leave a TODO comment)

Tests to add:
- purity_app/tests/test_panic_intervention.py (new):
  - _start_panic_intervention: with taskkill_processes and WebWatcherService monkeypatched, confirm session created in SELECTING_REASONS state, timer pill stopped, browser session cleared, panic.started emitted
  - Duplicate call: second _start_panic_intervention raises active window (mock isVisible), does not create second session

Validation:
- pytest purity_app/tests/test_panic_intervention.py
- python app.py: panic button appears bottom-right; pressing it kills Chrome (if open) and creates session without crashing
```

---

## Chat 4 — Reason dialog + intervention workspace

Paste into a new chat after Chat 3:

```text
Implement Phase 4 and Phase 5 from docs/TODO/2026-05-27_panic_button_plan.md.

Context: Chats 1–3 added domain model, stats, browser counters, panic button, and interruption handler. Read base_popup.py, web_popup.py, panic_session.py, panic_stats.py, and app.py before writing.

What to create:
- purity_app/ui/intervention/panic_reason_dialog.py
  - Extends BasePopup; WindowStaysOnTopHint
  - Checkable card buttons for reason IDs with display labels:
    home_alone/"Home Alone", triggering_content/"Triggering Content", tired/"Tired",
    hungry/"Hungry", biological_urge/"Biological Urge", lonely/"Lonely",
    discouraged/"Discouraged", anxious/"Anxious", angry/"Angry",
    avoiding_something/"Avoiding Something"
  - Optionally accepts a PanicStats instance; if top 2+ recurring reasons overlap with displayed choices, show gentle awareness copy (e.g. "Recent recurring struggle: Avoiding Something + Anxiety") using subdued muted-text styling
  - Awareness copy MUST NOT show counts; tone must be supportive and pastoral
  - "Help Me" button enabled only when ≥1 reason selected; disabled otherwise
  - On accept: exposes selected_reason_ids: list[str]

- purity_app/ui/intervention/panic_intervention_window.py
  - Top-level QMainWindow (not a dialog); WindowStaysOnTopHint
  - Header: progress label "0 / N topics" that updates as topics are reoriented
  - Body: one card per selected reason, each containing:
    - Bold topic label
    - Encouragement/scripture text (from a small static per-reason map defined in this file)
    - QTextEdit reflection field (placeholder: "Reflect here, or simply press Praise Jesus to continue…")
    - "Praise Jesus!" QPushButton
  - "Praise Jesus!" behaviour:
    - Call session.reorient_topic(reason_id, reflection_text)
    - If runtime journal available: emit panic.reflection_saved (if text non-empty), then panic.topic_acknowledged
    - Update progress label
    - Make that card's reflection field and button read-only/disabled
    - When all topics reoriented: transition session to COUNTDOWN, emit panic.countdown_started, replace UI with countdown view
  - Countdown view:
    - Large mm:ss QLabel updated every 1s via QTimer
    - Recovery prompts below (static list; do not rotate rapidly)
    - GUI-only "Notify Group For Prayer" button: emits panic.notify_group_clicked, shows brief confirmation text, sends nothing externally
    - On countdown complete: emit panic.countdown_completed; show "Close Session" button; hide timer
  - "Close Session": call session.close(PanicSessionOutcome.RECOVERED); emit panic.closed with outcome; close window

- Wire into app.py: replace the TODO comment in _start_panic_intervention with real PanicReasonDialog and PanicInterventionWindow instantiation

Tests to add:
- Extend purity_app/tests/test_panic_intervention.py:
  - PanicReasonDialog: selecting 0 reasons disables Help Me; selecting ≥1 enables it; awareness copy shown when stats report recurring reasons; awareness copy never shows numeric counts
  - PanicInterventionWindow: progress label updates on each Praise Jesus; countdown does not start before all topics reoriented; "Close Session" only appears after countdown completes; session outcome is RECOVERED on close

Validation:
- pytest purity_app/tests/test_panic_intervention.py
- python app.py: full intervention flow from panic button press to Close Session completes without error
```

---

## Chat 5 — Outcome wiring, log viewer, tone pass

Paste into a new chat after Chat 4:

```text
Implement Phase 6 (outcome wiring) and Phase 7 (log viewer verification) from docs/TODO/2026-05-27_panic_button_plan.md, then do a tone review pass.

Context: Chats 1–4 completed domain model, services, button, reason dialog, and intervention window. Read panic_session.py, panic_intervention_window.py, and log_viewer_window.py before writing.

What to change/verify:
1. Force-close handling: in PanicInterventionWindow.closeEvent, if session.state is not CLOSED: call session.close(PanicSessionOutcome.ABANDONED) and emit panic.closed with outcome=ABANDONED before accepting the event. Same in MainWindow.closeEvent if _active_panic_session is not closed.

2. Log viewer: confirm panic.jsonl appears under the correct date directory after a full test run. Run pytest purity_app/tests/test_log_viewer_window.py and add a test proving panic.reflection_saved events load and display as Intervention rows.

3. Tone review: audit all UI copy in panic_reason_dialog.py and panic_intervention_window.py:
   - Awareness copy must be pastoral, not numeric ("Recent recurring struggle: X + Y" is correct; "You triggered lonely 14 times" is not)
   - "Praise Jesus!" surrounding copy must feel warm and participatory, not mechanical or obligatory
   - Countdown prompts must feel calm and supportive (walk, pray, drink water, text someone, breathe)
   - "Notify Group For Prayer" confirmation text should be gentle: "Your group will be notified." not "Alert sent."
   - No UI copy should imply failure, punishment, or reset-to-zero framing

4. Run full test suite: pytest purity_app/tests/ and confirm no regressions in browser session, log viewer, or journal emitter tests.

Validation:
- All existing tests pass
- New panic tests pass
- Manual tone check: run app, trigger full panic flow, confirm emotional feel is supportive
```
