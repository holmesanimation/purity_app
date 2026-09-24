# 2026-05-27 Plan: Panic Button Implementation

> **Status: COMPLETE** — All 5 chats implemented. 188/188 tests passing as of 2026-05-27.

Implement the panic button as a first-class intervention workflow inside the running Purity app, reusing the existing MainWindow-owned browser control, shane_common JSONL journaling, Qt/PySide intervention UI patterns, and tray/runtime boundaries. The recommended approach is to ship a focused MVP first: persistent always-on-top panic button, immediate browser kill/session clear, reason selection, reflection/reorientation acknowledgements, countdown, local journal telemetry, explicit recovery outcomes, and a formal PanicSession state machine. Notification remains GUI-only in this pass. Durable JSONL remains the source of truth, with lightweight reason aggregates added for fast awareness insights.

## Decisions

- **Orchestration owner**: `MainWindow` in `app.py` — it already centralises browser process control, session state, runtime journaling, UI dialogs, and timers.
- **State machine**: Formal `PanicSessionState` enum from the start to prevent double-countdown, stale acknowledgements, and duplicate sessions.
- **Outcomes**: `PanicSessionOutcome` (RECOVERED, ESCALATED, ABANDONED, INTERRUPTED) modelled from day one and persisted in `panic.closed`.
- **Elevated telemetry**: `started_while_elevated` captured in `panic.started` — likely a high-value predictive signal.
- **Persistence**: Real `shane_common` JSONL journal events immediately. `FakeJournalService` is not acceptable for panic reflections.
- **Aggregates**: Lightweight `reason_id → count + last_seen_ts` store that complements journaling. Never stores reflection text.
- **Awareness copy**: Subtle and pastoral ("Recent recurring struggle: Avoiding Something + Anxiety"), never numerically confrontational ("You clicked lonely 14 times").
- **State naming**: Prefer emotionally softer `REFLECTION` / `REORIENTATION` over mechanical `REFLECTING` / `ACKNOWLEDGING`.
- **Notification**: GUI-only this pass. No Telegram, WeChat, auto-sends, or accountability escalation.
- **End state**: Close Session only. Do not offer Restore Browser.
- **Deferred**: Persistent desktop stickies, Leave Computer Confirmed button, cooldown interruption guard, outbound notification, AI/insights service — all post-MVP.
- **Encouragement rotation**: Slow and quiet. For stickies: 30–60 minutes maximum or user-initiated.

## Phases

### Phase 0 — Domain model, state machine, journal taxonomy

New file: `purity_app/services/panic_session.py`

- `PanicSessionState`: `INTERRUPTING`, `SELECTING_REASONS`, `REFLECTION`, `REORIENTATION`, `COUNTDOWN`, `POST_RECOVERY`, `CLOSED`
- `PanicSessionOutcome`: `RECOVERED`, `ESCALATED`, `ABANDONED`, `INTERRUPTED`
- `PanicSession` model/controller owns: `panic_session_id`, selected reasons, reflections keyed by `reason_id`, reoriented reason IDs, countdown status, notify stub state, `started_while_elevated`, current state, final outcome
- Guarded transitions: countdown cannot start twice; reorientation cannot mutate closed sessions; duplicate panic request raises active workflow

Update `purity_app/services/journaling_profile.py` — new kind constants:

```
panic.started
panic.state_changed
panic.reasons_selected
panic.reflection_saved
panic.topic_acknowledged
panic.countdown_started
panic.countdown_completed
panic.closed
panic.notify_group_clicked
panic.danger_elevated
panic.danger_cleared
```

Update `purity_app/services/journal_events.py` (or add `panic_events.py`):

- Emitters for every kind above
- `panic_session_id` on every payload; `correlation` field linking all events in one session

Update `purity_app/services/log_kind_map.py`:

- `KindSpec` for each panic kind
- Classify all `panic.*` as `TYPE_INTERVENTION`

Payload discipline: reasons as stable IDs + labels; reflections keyed by `reason_id`; reorientation counts; countdown seconds; browser/session context; `started_while_elevated`; final outcome; `notify_stub_clicked` boolean.

### Phase 1 — Settings, recurrence aggregates, browser override signal

Update `purity_app/services/settings_schemas.py`:

- `panic_cooldown_seconds` default `300`
- `panic_auto_accountability_enabled` default `true` (stub only, not wired)

New file: `purity_app/services/panic_stats.py`

- Persists to `<data_root>/data/panic/reason_counts.json`
- Schema: `reason_id → {count, last_seen_ts}`, optional co-occurrence counts
- Updated when a session commits selected reasons
- Never stores reflection text

Update `purity_app/services/browser_session.py` — `allow_url()`:

- Adds `override_count`, `last_override_ts`, `last_override_url` to `active_session.json`

Update `MainWindow`:

- Poll active session state (existing cadence or small timer)
- When `override_count` increases: set panic button elevated, emit `panic.danger_elevated`
- Clear elevated state when browser session clears
- Do not call Qt from `BrowserSessionApiServer` request thread

### Phase 2 — Persistent panic button

New file: `purity_app/ui/intervention/panic_button.py`

- Small frameless, always-on-top, bottom-right `QWidget`/`QToolButton`
- Semi-transparent default; fully opaque on hover
- Signals: `panic_requested`
- Method: `set_elevated(bool)`
- Instantiated from `MainWindow` after `_web_timer_pill` setup
- Primary screen `availableGeometry` for initial placement
- Wired to `MainWindow._start_panic_intervention()`

### Phase 3 — Immediate interruption

`MainWindow._start_panic_intervention()`:

1. If active panic session already exists → raise its window, return
2. Create `PanicSession` in `INTERRUPTING` state
3. Capture `started_while_elevated`
4. `taskkill_processes(_WATCHED_BROWSERS)`
5. `_web_timer_pill.stop_session()`
6. `_browser_session_manager.clear_session()`
7. Clear `_web_session_*` fields
8. Emit `panic.started` with `started_while_elevated` in payload
9. Transition to `SELECTING_REASONS`

Keep synchronous and fast before any dialog appears.

### Phase 4 — Reason selection with subtle recent-cause awareness

New file: `purity_app/ui/intervention/panic_reason_dialog.py`

- `BasePopup` conventions; `WindowStaysOnTopHint`
- Checkable cards for stable reason IDs:
  `home_alone`, `triggering_content`, `tired`, `hungry`, `biological_urge`,
  `lonely`, `discouraged`, `anxious`, `angry`, `avoiding_something`
- Reads `panic_stats` and shows subtle pastoral awareness copy if applicable
- "Help Me" enabled when ≥ 1 reason selected
- On commit: transition to `REFLECTION`/`REORIENTATION`, emit `panic.reasons_selected`, update aggregates

### Phase 5 — Help workspace and reorientation flow

New file: `purity_app/ui/intervention/panic_intervention_window.py`

- Progress indicator (n/total topics reoriented)
- Recovery instructions
- GUI-only "Notify Group For Prayer" button (emits `panic.notify_group_clicked`, no external send)
- Topic panels for each selected reason:
  - Topic label + encouragement/scripture
  - `QTextEdit` reflection field
  - "Praise Jesus!" button
- "Praise Jesus!" behaviour:
  - Saves reflection if present (emit `panic.reflection_saved`)
  - Marks topic reoriented in `PanicSession` (emit `panic.topic_acknowledged`)
  - Updates progress
  - Locks panel (read-only)
  - Tone: warm, participatory, non-punitive — not mechanical/legalistic

### Phase 6 — Countdown, close session, recovery outcome

- Countdown starts only after `PanicSession` confirms all topics reoriented → transitions to `COUNTDOWN`
- `panic.countdown_started` emitted
- Topic panels become read-only; browser session stays cleared
- Large `mm:ss` display; slow recovery prompts (walk, pray, drink water, message someone, breathe)
- On countdown completion → `POST_RECOVERY`; active controls → "Close Session"
- `panic.countdown_completed` emitted
- "Close Session" → `PanicSession.outcome = RECOVERED`; `panic.closed` with outcome
- Force-close mid-session → best-effort `panic.closed` with `ABANDONED`/`INTERRUPTED` in cleanup
- No "Restore Browser" offered

### Phase 7 — Journaling upgrade path

- Panic reflections persist to `<data_root>/_system/purity/journals/<date>/panic.jsonl`
- Log viewer automatically picks them up as `Intervention` rows
- After MVP: replace `FakeJournalService` in `journal_panel.py` with disk-backed reader replaying `journal.entry` + `panic.reflection_saved` events
- Privacy: consider redaction option before surfacing reflection text in analytics

### Phase 8 — Delay persistent recovery sticky

Do not ship desktop stickies in MVP. Defer until:

- Core flow is emotionally validated
- Multi-monitor, z-order, focus stealing, stale state, clutter fatigue, and restart behaviour are each addressed

### Phase 9 — Future notification/accountability integration

- "Notify Group" remains GUI-only stub
- Later: `NotificationService` interface, provider implementations (Telegram etc.), preview/edit/confirm before any send
- Automatic escalation only after notification infrastructure and privacy expectations are defined

### Phase 10 — Future Intervention Engine boundary

- `MainWindow` orchestration is correct for MVP
- Future extraction: `InterventionEngine` owns escalation logic, countdown state, danger scoring, recurrence analytics, and telemetry
- UI layer owns dialogs, floating button, stickies, countdown rendering

### Phase 11 — Future cooldown interruption guard (deferred)

- Detect browser reopen during `COUNTDOWN` via existing `WebWatcherService` path
- Response: show "You are still in recovery mode" copy; optionally restart/extend countdown or move outcome to `ESCALATED`
- Not MVP; only if browser reopen during countdown proves common in real use

### Phase 12 — Future advisory Intervention Insights Service (deferred)

- Consumes recurrence aggregates, journal events, timestamps, browser escalation, panic outcomes
- Produces: gentle insights, pre-emptive reminders, support recommendations, scripture surfacing, accountability prompts
- Must remain advisory and supportive, never authoritarian

## Relevant files

| File | Role |
|---|---|
| `purity_app/app.py` | `MainWindow` — orchestration owner for MVP |
| `purity_app/services/panic_session.py` | **New** — state machine, model, outcome tracking |
| `purity_app/services/panic_stats.py` | **New** — lightweight aggregate store |
| `purity_app/services/intervention_insights.py` | **Future** — advisory insights service |
| `purity_app/ui/intervention/panic_button.py` | **New** — persistent floating button |
| `purity_app/ui/intervention/panic_reason_dialog.py` | **New** — reason selection with awareness copy |
| `purity_app/ui/intervention/panic_intervention_window.py` | **New** — help workspace, reorientation, countdown |
| `purity_app/ui/intervention/base_popup.py` | Base dialog pattern to follow |
| `purity_app/ui/intervention/web_popup.py` | Reference for topmost dialogs and styling |
| `purity_app/ui/web_timer_pill.py` | Reference for floating always-on-top lifecycle |
| `purity_app/services/browser_session.py` | Add override counters to `allow_url()` |
| `purity_app/services/browser_session_api_server.py` | Thread boundary — no Qt calls from handler |
| `purity_app/browser_extension/background.js` | Whitelist override flow → elevated danger state |
| `purity_app/services/runtime.py` | Journal and `run_id` source |
| `purity_app/services/journaling_profile.py` | Add panic kind constants |
| `purity_app/services/journal_events.py` | Add panic emitters |
| `purity_app/services/log_kind_map.py` | Classify panic events as Intervention |
| `purity_app/services/settings_schemas.py` | Add panic settings |
| `purity_app/ui/system/log_viewer_window.py` | Disk replay picks up panic.jsonl automatically |
| `purity_app/ui/reflection/journal_panel.py` | Upgrade from FakeJournalService post-MVP |
| `purity_app/services/fake_journal.py` | In-memory surface — not for panic persistence |
| `shane_common/src/shane_common/journaling/service.py` | Reuse, do not replace |

## Verification

1. **State-machine unit tests**: legal transitions; duplicate countdown prevention; reorientation after close rejected; `started_while_elevated` persisted; final outcome assigned; duplicate panic request raises existing window.
2. **Journal emitter tests**: `pytest purity_app/tests/test_purity_journal_events.py purity_app/tests/test_purity_startup_journal.py`
3. **BrowserSession tests**: `allow_url()` increments `override_count`, records `last_override_url`/`last_override_ts`, does not break `allowed_urls` behaviour.
4. **panic_stats tests**: counts increment, persist, reload correctly; reflection text never stored.
5. **Qt widget tests**: `PanicReasonDialog` selection state and subtle awareness rendering; `PanicInterventionWindow` progress/countdown using a short test countdown.
6. **MainWindow orchestration tests**: monkeypatch `WebWatcherService` and `taskkill_processes`; confirm browsers killed, session cleared, timer pill stopped, `PanicSession` created, `panic.started` emitted.
7. **Log viewer tests**: `panic.*` disk events load and classify as Intervention rows.
8. **Future cooldown test**: browser reopen during `COUNTDOWN` → recovery-mode handling, not normal browsing.
9. **Manual smoke test (Windows)**: press panic button; Chrome closes immediately; reason dialog appears on top; acknowledgements unlock countdown; Close Session appears; Chrome not restored.
10. **Manual extension smoke test**: start approved session; attempt non-whitelisted URL; click Yes; confirm panic button enters elevated state; confirm state clears on session end.
11. **Manual tone check**: "Praise Jesus!" acknowledgement, recurrence awareness copy, and countdown prompts feel supportive and non-punitive.

## Gotchas and Areas for Improvement

1. Always-on-top widgets fight multi-monitor positioning and Windows taskbar geometry. Start with `primaryScreen().availableGeometry()`, harden later.
2. Browser kill is forceful and may close unrelated tabs. Keep it explicit, journaled, limited to `_WATCHED_BROWSERS`.
3. Reflection text in JSONL needs careful handling in any viewer, analytics, or sync surface.
4. `BrowserSessionApiServer` handles HTTP off the Qt thread — no direct Qt mutations from handler code.
5. Separate sticky-note windows add lifecycle complexity. Ship topic panels inside one intervention window first; split into stickies only after behaviour is validated.
6. Recurrence aggregates become emotionally loaded if surfaced bluntly. Use them for gentle awareness only.
7. `FakeJournalService` means dashboard journal entries are not durable. Panic work should trigger the real journal upgrade.
8. Repeated-panic automatic notification must wait until outbound infrastructure, preview/confirm flow, and privacy expectations are defined.
9. An `InterventionEngine` extraction boundary will be needed as escalation, analytics, and AI support chat share intervention intelligence.
10. Browser reopen during countdown is a future edge case: frame as recovery-mode protection, not shame.
11. Any AI/insights layer must be advisory and user-supportive, not authoritarian.
