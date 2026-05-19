# 2026-05-18 Plan: Introduce shane_common

Create `D:\code\git\shane_common` as a third, dependency-neutral Python package for generic infrastructure only. The first pass should not modify trading_platform files while that project is still rooted at `D:\code\git`; once the move is complete, treat `D:\code\git\trading_platform` as the repo root. Do not extract trading-specific journaling/supervisor/settings wholesale, and use `purity_app` as the initial integration target because it is smaller and currently has duplicated primitives. The recommended approach is to stand up `shane_common` with stable low-level utilities first, migrate `purity_app` behind thin adapters, and later integrate `trading_platform` one generic primitive at a time after parity tests prove behavior is unchanged.

## Audit Findings
- `purity_app` is a small script-style app with duplicated logic across `focus_guard.py`, `focus_guard_chrome_trigger.py`, and `reminder_dialog.py`.
- `app.py` is the current tray/bootstrap entrypoint. It owns Chrome process polling, timer loop startup, tray menu commands, reload, quit, and reset-now actions.
- `reminder_dialog.py` owns most active behavior: constants, JSON belief/scripture config load/save/normalization, state reset by date, hydration/vitamin calculations, Tk config window, Tk reset popup, Windows Chrome window disable/enable helpers, JSONL popup event logging, and popup locking.
- `chrome_dialog.py` owns a smaller Chrome gate popup and uses `reminder_dialog` Windows helpers, which couples UI, process control, and platform helpers.
- `focus_guard.py` and `focus_guard_chrome_trigger.py` look like older/alternate entrypoints that duplicate config, config persistence, logging, popup, tray, process polling, and single-instance guard logic.
- `gui/` is empty.
- `planning/purity_app_product_system_architecture_journal_v_1.md` already recommends a shared package direction and warns to extract only after both apps genuinely need the abstraction.
- `D:\code\git\shane_common` now exists as the shared-package repo root.
- Reference-only `trading_platform` already has substantial local implementations: `journaling/json_safety.py`, `journaling/envelope.py`, `journaling/service.py`, `journaling/sinks/jsonl_sink.py`, `settings/manager.py`, `settings/models.py`, `notify/notify_manager.py`, `notify/contracts.py`, `supervisor/heartbeat_writer.py`, `supervisor/state_store.py`, `utils/time_utils.py`, and `utils/day_bucket.py`. These are useful evidence for overlap, but many are trading-shaped and should not be lifted wholesale.

## Proposed shane_common Structure
1. `pyproject.toml` - package metadata, Python version target, pytest config, optional dependency groups.
2. `src/shane_common/__init__.py` - package marker and version export only.
3. `src/shane_common/time.py` - UTC timestamp helpers, day buckets, optional epoch normalization.
4. `src/shane_common/json_safety.py` - JSON-safe coercion for datetimes, enums, bytes, sets/tuples, NaN/Inf, dataclasses.
5. `src/shane_common/io/atomic.py` - atomic JSON/text writes with Windows `os.replace` retry.
6. `src/shane_common/io/json_files.py` - `load_json_file`, `save_json_file_atomic`, default fallback behavior.
7. `src/shane_common/events/jsonl.py` - append-only JSONL writer and simple event envelope helpers.
8. `src/shane_common/config/json_config.py` - small JSON config repository pattern with normalize/default callbacks.
9. `src/shane_common/runtime/single_instance.py` - port/socket lock or file lock helper, configurable app id/port/path.
10. `src/shane_common/processes/windows.py` - Windows process discovery and visible-window enable/disable helpers behind safe no-op stubs on non-Windows.
11. `src/shane_common/processes/polling.py` - generic process-running checks and edge-triggered poll loop primitives.
12. `src/shane_common/scheduling/loops.py` - simple daemon loop runner and periodic timer primitives.
13. `src/shane_common/notifications/contracts.py` - generic notification dataclass/severity only, not adapter-specific delivery in v1.
14. `src/shane_common/db/sqlite.py` - later-phase SQLite connection/repository helpers, not part of the first purity migration unless needed.
15. `tests/` - unit tests for pure utility behavior, plus temp-file persistence tests.

## Candidate APIs To Extract
1. JSON safety: `sanitize_json(value)`, `utc_now_iso()`, `day_bucket_from_ts(ts)`, `normalize_epoch_seconds(value)`. Source evidence: `trading_platform.journaling.json_safety.sanitize_json`, `trading_platform.utils.time_utils`, `trading_platform.utils.day_bucket`, and `purity_app` JSONL writing.
2. Atomic file writes: `write_json_atomic(path, data, *, retries=5, delay=0.05, sort_keys=True)`, `write_text_atomic(path, text, ...)`. Source evidence: `trading_platform.supervisor.heartbeat_writer._write_atomic`, `trading_platform.supervisor.state_store._atomic_write_json`, `trading_platform.settings.manager.save`, and `trading_platform.settings.schedule_manager.save`.
3. JSON config repository: `JsonConfigStore(path, default_factory, normalize, to_json_ready=None)` with `load()` and `save(config)`. Source evidence: `purity_app.reminder_dialog.load_belief_scripture_config`, `save_belief_scripture_config`, `normalize_belief_config`, `config_to_json_ready`.
4. Append-only JSONL events: `JsonlEventWriter(path_factory, sanitize=True, ensure_ascii=False)`, `append(record)`, optionally `MonthlyJsonlPath(root, prefix)`. Source evidence: `purity_app.reminder_dialog.append_focus_log`, `get_log_path`, `trading_platform.journaling.sinks.JsonlSink`, `trading_platform.persistence.webhook_capture.WebhookCapture`, `trading_platform.supervisor.state_store` audit files.
5. Process/window helpers: `is_process_running(image_name)`, `taskkill_processes(image_names)`, `list_process_pids(image_name)`, `enum_visible_windows_for_pids(pids)`, `disable_windows(hwnds)`, `enable_windows(hwnds)`. Source evidence: `purity_app.app.is_chrome_running`, `purity_app.focus_guard_chrome_trigger.get_chrome_pids`, `_enum_windows_for_pids`, `disable_windows`, `enable_windows`, `chrome_dialog._kill_chrome`.
6. Edge-triggered process monitor: `ProcessOpenWatcher(process_names, poll_seconds, cooldown_seconds, on_opened, reset_cooldown_on_close=True)`. Source evidence: `purity_app.app.chrome_watch_loop`, `focus_guard_chrome_trigger.chrome_watch_loop`.
7. Single-instance guard: `SocketSingleInstanceGuard(host, port)` or `single_instance_or_exit(app_id, port=None)`. Source evidence: `purity_app.focus_guard.already_running` and `focus_guard_chrome_trigger.already_running`. This should be configurable to avoid hard-coded port collisions.
8. Generic notification contracts: `NotificationSeverity`, `NotificationEvent`, and dedupe/windowing helper later. Source evidence: `trading_platform.notify.contracts.NotificationEvent`, `NotifyManager`; future `purity_app` accountability notifications. Do not pull Bark/Telegram/trading app integration yet.
9. SQLite primitives later: `SQLiteEventRepository`, `FeedbackRepository`, `NotificationOutboxRepository`, migration runner. Source evidence: product plan’s shared SQL layer and both apps’ likely need for feedback/events/notifications. Defer until after JSONL/config extraction proves useful.

## Explicit Non-Candidates For Early Extraction
- Trading taxonomy, audit envelope contract, broker/source/instrument layout, strategy schedules, supervisor liveness models, risk locks, broker timestamps, order/capital/account concepts.
- Purity spiritual content, belief categories, scripture lists, reset popup layout, hydration/vitamin domain rules, Chrome intent categories, purity event schema details.
- PySide/Tk UI components, tray menu UI, and domain-specific dialogs. Keep UIs app-owned.

## Migration Phases
1. Phase 0 - Baseline audit and tests. Add lightweight characterization tests around `purity_app` pure functions before migration: belief config normalization, scripture selection behavior, expected water calculation with injectable time if practical, JSONL record shape helper if extracted locally first. Dependency: none.
2. Phase 1 - Stand up `D:\code\git\shane_common` package. Create src-layout package, pytest, README, and pure utility modules for time, JSON safety, atomic writes, JSON config store, JSONL event writer. Dependency: Phase 0 findings, but can be built in parallel with purity tests.
3. Phase 2 - Use `shane_common` in `purity_app` for persistence only. Replace `get_log_path`/`append_focus_log` with `JsonlEventWriter` or a tiny app adapter. Replace direct config JSON load/save with `JsonConfigStore` while leaving `normalize_belief_config` and domain defaults inside `purity_app`. Dependency: Phase 1.
4. Phase 3 - Migrate process/window primitives. Move Chrome PID/window enable-disable and process-running/taskkill logic behind `shane_common.processes`. Keep Chrome policy and dialog decisions in `purity_app`. Dependency: Phase 1; can run after or parallel with Phase 2 if tests are in place.
5. Phase 4 - Reduce duplicate entrypoints. Decide whether `focus_guard.py` and `focus_guard_chrome_trigger.py` are obsolete compatibility entrypoints or should import the same canonical modules as `app.py`/`reminder_dialog.py`. Prefer deprecating duplicates after parity is verified. Dependency: Phases 2-3.
6. Phase 5 - Add generic notification contracts/outbox only when purity accountability notifications are started. Use manual-first prayer request flow in `purity_app`; do not import trading notification adapters. Dependency: product decision to build notification feature.
7. Phase 6 - Add SQLite primitives when the goals/feedback/review systems need queryable state. Start with generic `app_events`, `feedback_items`, and `notifications` tables, but keep schema migrations app-owned until both apps use them. Dependency: actual feature demand.
8. Phase 7 - Later `trading_platform` integration. In a separate pass, install `shane_common` editable in `trading_platform`, then migrate one utility at a time behind compatibility wrappers. Start with JSON safety/time/atomic writes if tests pass. Leave existing trading module public APIs intact until downstream imports are updated. Dependency: no earlier than stable `shane_common` release from purity integration.

## Files Likely Touched In purity_app
- `D:\code\git\purity_app\app.py` - Chrome watcher can use generic process polling; tray/bootstrap remains app-owned.
- `D:\code\git\purity_app\reminder_dialog.py` - config load/save, JSONL logging, Windows Chrome window helpers, and possibly date/time helpers migrate behind common utilities; popup UI and purity-specific rules stay here initially.
- `D:\code\git\purity_app\chrome_dialog.py` - process kill and window enable/disable can use common process/window utilities; Chrome gate UI and policy stay app-owned.
- `D:\code\git\purity_app\focus_guard.py` - either refactor to reuse canonical modules or mark as legacy; currently duplicates much of `reminder_dialog.py` and app/tray logic.
- `D:\code\git\purity_app\focus_guard_chrome_trigger.py` - same as `focus_guard.py`; likely legacy or alternate all-in-one entrypoint.
- `D:\code\git\purity_app\docs\planning\purity_app_product_system_architecture_journal_v_1.md` - optionally update later with actual package decisions if implementation occurs. Do not update during plan-only work.
- New future files likely: `D:\code\git\purity_app\requirements.txt` or `pyproject.toml` if dependency management is formalized, and local tests under `D:\code\git\purity_app\tests\`.

## Later trading_platform Integration Plan
1. Do not modify trading_platform files in the current pass. While the project is still temporarily rooted at `D:\code\git`, treat that whole tree as off-limits except for the later planned move; after the move, the repo root becomes `D:\code\git\trading_platform`.
2. Create a compatibility inventory: map `trading_platform.journaling.json_safety.sanitize_json`, `utils.time_utils`, `utils.day_bucket`, atomic write helpers, and notification contracts to candidate `shane_common` equivalents.
3. Add `shane_common` as an editable/dev dependency in a dedicated trading-platform branch/pass only after `shane_common` has its own test suite and versioned API.
4. Migrate lowest-risk utilities first: `sanitize_json`, UTC/day bucket helpers, and atomic JSON writes. Keep wrappers in existing trading modules so internal imports do not churn.
5. Run full existing trading tests after each utility migration. If wrappers reveal behavior differences, either preserve trading behavior in wrappers or add optional knobs to `shane_common`; do not force trading to match purity behavior.
6. Consider notification contracts only after verifying `purity_app` needs the same severity/event/dedupe concepts. Keep Bark/Telegram adapters trading-owned until purity needs a generic adapter abstraction.
7. Do not migrate journaling envelope/layout/taxonomy, supervisor state models, risk lock semantics, strategy schedule management, broker clock normalization beyond generic epoch helpers, or any trading domain contracts.

## Risks Around Over-Abstraction
1. Trading-shaped leakage: if `shane_common` adopts `broker`, `instrument`, `strategy`, `run_id`, or supervisor liveness concepts too early, purity will inherit irrelevant complexity.
2. Purity-shaped leakage: if `shane_common` learns about scripture, temptation, hydration, Chrome categories, or prayer requests, trading becomes an awkward consumer.
3. Premature stable API burden: once both apps import shared functions, changing signatures becomes slower. Keep v1 modules small and documented.
4. Behavioral drift during migration: persistence and process helpers are easy to subtly change, especially Windows `os.replace`, tasklist parsing, and JSON serialization.
5. Dependency bloat: shared package should stay standard-library-first. Optional UI, pandas, PySide, pystray, PIL, or notification adapter dependencies should not be core dependencies.
6. Import direction mistakes: `shane_common` must never import from `purity_app` or `trading_platform`; app-specific adapters should live in each app.
7. False reuse: duplicate code is not enough reason to extract if the policies differ. Extract mechanisms, not domain decisions.

## Test Strategy
1. `shane_common` unit tests: `sanitize_json`, UTC timestamp/day bucket helpers, epoch normalization, atomic write success/failure cleanup, JSON config load fallback/save round-trip, JSONL append format, Windows retry behavior with monkeypatched `os.replace`, and no-op behavior for non-Windows process/window helpers.
2. `purity_app` characterization tests before migration: belief config normalization accepts dict/list/tuple scriptures, string/list keywords, invalid config fallback, `config_to_json_ready` shape, empty/fallback/belief-keyword scripture selection, monthly JSONL path naming, and Chrome watcher cooldown state via injected process state if refactored.
3. `purity_app` migration tests after each phase: same tests pass with common utilities; temp directories prove config/log writes do not touch the real home directory.
4. Manual smoke tests for purity: launch app, tray menu appears, reset popup opens, countdown completes, water/vitamin gating still works, belief scripture updates while typing, log line is appended, Chrome open dialog appears, Chrome windows re-enable after close/cancel/Need/non-Need path.
5. `trading_platform` later tests: run existing test suite unchanged after wrappers switch to `shane_common`; add golden tests for `sanitize_json`, atomic writes, JSONL sink outputs, notification event IDs, and settings/schedule persistence before swapping internals.
6. Packaging tests: `pip install -e D:\code\git\shane_common`, import from a clean Python process, and verify both apps can import without circular dependencies.

## Decisions
- Start with generic infrastructure only: JSON safety, file I/O, JSON config, JSONL appenders, time helpers, process/window helpers, and simple runtime guards.
- `purity_app` is the first integration target because it is compact and has duplicated infrastructure.
- `trading_platform` remains reference-only in this pass and should later integrate through compatibility wrappers, not bulk rewrites.
- Domain models, UI, spiritual content, trading audit contracts, and supervisor/risk systems stay app-owned.
- Keep `shane_common` standard-library-first; add optional extras only when a real shared need appears.

## Further Considerations
1. Decide whether `purity_app` should gain a formal `pyproject.toml` before migration. Recommendation: yes, because editable dependency management becomes cleaner.
2. Decide whether `focus_guard.py` and `focus_guard_chrome_trigger.py` are legacy. Recommendation: treat them as legacy candidates and converge on `app.py` plus app-owned modules before deep feature work.
3. Decide when SQLite enters. Recommendation: defer until goals, feedback, notifications, or reviews need queryable state; JSONL remains enough for current audit/event logging.
