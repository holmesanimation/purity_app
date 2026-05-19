# 2026-05-18 Chat Snippets: Introduce shane_common

Minimum recommended chats now: 3.

Why 3 chats:
- Chat 1 covers the smallest high-value foundation slice: characterization tests plus initial `shane_common` package scaffolding.
- Chat 2 focuses only on persistence migration so validation stays narrow and the diff stays reviewable.
- Chat 3 isolates Windows process helpers and duplicate-entrypoint cleanup, which is the riskiest behavioral slice.
- Phases 5-7 are explicitly deferred and should become separate future chats only when those features are actually started.

## Chat 1 - Characterization tests and package scaffold
Paste this into a new chat:

```text
Implement only Phase 0 and Phase 1 from [docs/TODO/2026-05-18_shane_common_plan.md](docs/TODO/2026-05-18_shane_common_plan.md).

Constraints:
- Do not modify trading_platform files while that project is still rooted at D:\code\git. After the folder move, treat D:\code\git\trading_platform as the repo root.
- Keep shane_common dependency-neutral and standard-library-first.
- Start from the most local code paths in purity_app that control config normalization, scripture selection, and JSONL path/log behavior.
- Add the smallest useful characterization tests in purity_app first.
- Then scaffold D:\code\git\shane_common with pyproject, src layout, README if needed, and initial pure utility modules/tests for time, JSON safety, atomic writes, JSON file helpers, JSON config store, and JSONL event writing.
- Do not migrate purity_app to use shane_common yet.
- Validate with the narrowest relevant test commands after the first edit and again at the end.

Deliverables:
- Working tests for the touched slices.
- A minimal, importable shane_common package with passing unit tests.
- A concise summary of what was implemented, what was deferred, and any blockers.
```

## Chat 2 - Persistence migration only
Paste this into a new chat after Chat 1 is complete:

```text
Implement only Phase 2 from [docs/TODO/2026-05-18_shane_common_plan.md](docs/TODO/2026-05-18_shane_common_plan.md).

Context:
- Assume Chat 1 already created the initial shane_common package and tests.
- Read the current purity_app code and use the existing shane_common utilities rather than re-implementing them locally.

Constraints:
- Limit scope to persistence only.
- Replace purity_app JSON config load/save paths with a thin adapter over JsonConfigStore while keeping purity-specific defaults, normalization, and schema decisions inside purity_app.
- Replace JSONL append/path logic with JsonlEventWriter or a very small app-owned adapter.
- Do not touch trading_platform.
- Do not start process/window helper extraction yet.
- Preserve current behavior and file formats unless a failing test proves a change is needed.

Validation:
- Run the narrowest relevant purity_app tests immediately after the first substantive edit.
- Add or update tests only for this persistence slice if needed.

Deliverables:
- Minimal code changes wired through shane_common for persistence.
- Focused validation results.
- A short note on any behavior preserved intentionally for parity.
```

## Chat 3 - Process helpers and duplicate entrypoint reduction
Paste this into a new chat after Chat 2 is complete:

```text
Implement Phase 3 and the smallest justified part of Phase 4 from [docs/TODO/2026-05-18_shane_common_plan.md](docs/TODO/2026-05-18_shane_common_plan.md).

Constraints:
- Extract only generic Windows process/window primitives and process polling helpers into shane_common.
- Keep Chrome-specific policy, UI, and purity-domain decisions inside purity_app.
- Do not modify trading_platform files while that project is still rooted at D:\code\git. After the folder move, treat D:\code\git\trading_platform as the repo root.
- After process helpers are integrated, reduce duplication across app.py, focus_guard.py, and focus_guard_chrome_trigger.py only as far as needed to converge on one canonical implementation path or clearly mark legacy wrappers.
- Do not start notification or SQLite work.

Validation:
- After the first substantive edit, run the narrowest executable validation for the touched process/polling slice.
- Re-run focused tests after each repair if validation fails.
- If there is no reliable automated coverage for a Windows-specific branch, state that clearly and do the narrowest available validation plus a brief manual smoke-test checklist.

Deliverables:
- Generic shane_common process helpers used by purity_app.
- Reduced duplicate entrypoint risk without broad rewrites.
- Clear summary of what remains deferred from later phases.
```

## Deferred future chats
Do not start these until there is real demand:
- Phase 5 notification contracts/outbox.
- Phase 6 SQLite primitives.
- Phase 7 trading_platform integration.
