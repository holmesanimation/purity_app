# Purity App Local + Dropbox Backup — Implementation Plan v1.0

**Date:** 2026-09-15
**Status:** P0–P6 COMPLETE · Post-P6 Monthly Disaster Recovery Drill COMPLETE

## Synopsis

Purity data (notes, Bible library/memorizing list, prayer recipients/cycle
state, tag library, reminders override, preferences) is currently unbacked
up. This plan implements COPY_ONLY verified backup to a configured secondary
local drive first (P1), then wires it into the existing `app.py`
tray/status UI (P2), adds a weekly schedule (P3), adds Dropbox as an
independent second destination (P4), hardens reliability (P5), and proves
restore actually works (P6). Guided check-ins have no durable store today
and are explicitly excluded/flagged, not silently treated as backed up.

Governing inputs:
- [2026-09-15_Purity_App_Local_and_Dropbox_Backup_Revised_Scaled_Down_Phased_Plan_v2_0.md](../03_ACTIVE_WORK/2026-09-15_Purity_App_Local_and_Dropbox_Backup_Revised_Scaled_Down_Phased_Plan_v2_0.md)
- [2026-09-15_Purity_App_Backup_Phase_P0_Repository_Audit_v1_0.md](../03_ACTIVE_WORK/2026-09-15_Purity_App_Backup_Phase_P0_Repository_Audit_v1_0.md)

```text
P0 — COMPLETE
P1 — NEXT
P2–P6 — PLANNED
```

---

## P0 — Repository / persistence / supervisor / shane_common audit

**Status: COMPLETE.** See the P0 audit document above. Do not repeat it.
Key accepted findings carried forward into every later phase:

- Execution owner is the main `app.py` QApplication process, not
  `supervisor.py`. `supervisor.py` stays a crash-detection watchdog only.
- `PurityTrayApp` already runs in-process inside `app.py`.
- Backup filesystem/hash/cloud work must never run on the Qt GUI thread.
- A plain-Python `BackupService` owns backup orchestration; Qt code never
  touches files/hashes/network directly.
- Reuse `shane_common.runtime.transfer.copy_file_verified()`,
  `shane_common.runtime.transfer.hashing.sha256_file()`,
  `shane_common.io.atomic.write_json_atomic()` / `write_text_atomic()`,
  and optionally `shane_common.watchdog.audit.AppendOnlyAuditLog`.
- No generic single-flight lock, schedule/due-occurrence primitive, or
  Dropbox/credential abstraction exists in `shane_common` today — build
  Purity-local first; only promote later if a second consumer appears.
- `TagLibrary` (`purity_app/data/tags.json`) and Notes JSONL live outside
  `data_root` (hardcoded repo-relative paths) — the catalog must reference
  them explicitly.
- `BibleLibrary._save()` and `TagLibrary._save()` are non-atomic
  (`Path.write_text()`), so a copy taken mid-write can read a torn file;
  `copy_file_verified`'s hash mismatch handling plus a bounded retry covers
  this — no new low-level write fix is required here.
- Guided check-ins have no durable store (`_save_guided()` only updates an
  in-memory service) — this is a pre-existing product gap, excluded from
  backup scope, not silently claimed as covered.

---

## P1 — Manual verified local backup — NEXT

### Objective
Implement a working, tested, verified COPY_ONLY backup of all
restore-required Purity families to one configured secondary local drive,
callable manually (no UI yet), with durable run-history state.

### Existing infrastructure reused
- `shane_common.runtime.transfer.copy_file_verified()` — copy + size +
  SHA-256 source/destination verification, source-change and
  destination-conflict detection already handled.
- `shane_common.runtime.transfer.hashing.sha256_file()` — standalone verify.
- `shane_common.io.atomic.write_json_atomic()` — durable run-state file.
- `shane_common.watchdog.audit.AppendOnlyAuditLog` — optional run-history
  audit trail (decide during implementation; not mandatory for P1).
- `services.settings_schemas.resolve_purity_data_root()` — resolve
  `<data_root>`-relative families at runtime; never hardcode the root.
- `shane_common.preferences.manager.SettingsManager` — add one new setting
  for the local destination path (`backup_local_destination`), same pattern
  as existing settings.

### Files/modules likely added or modified
```text
purity_app/services/backup/__init__.py
purity_app/services/backup/catalog.py         # PurityBackupCatalog
purity_app/services/backup/models.py           # BackupRunResult, FamilyResult, enums
purity_app/services/backup/service.py          # BackupService
purity_app/services/backup/state.py            # run-history persistence
purity_app/services/backup/destinations/__init__.py
purity_app/services/backup/destinations/local.py   # LocalFilesystemDestination
purity_app/services/settings_schemas.py        # add backup_local_destination setting
purity_app/tests/backup/test_catalog.py
purity_app/tests/backup/test_service.py
purity_app/tests/backup/test_state.py
```

### Important contracts/classes/functions
- `PurityBackupCatalog.discover() -> list[BackupSourceFamily]` — resolves the
  fixed family list below against real filesystem paths at call time
  (calls `resolve_purity_data_root()`, does not cache the root at import
  time).
- `BackupSourceFamily(name, paths, required: bool)`.
- `BackupService.run(destination_root: Path) -> BackupRunResult` — iterates
  catalog families, calls `copy_file_verified()` per file, aggregates
  counts, persists result via `state.py`.
- `BackupRunResult(run_id, started_at, completed_at, status, file_count,
  verified_count, failed_count, bytes_copied, last_error, family_results)`.
- `FamilyResult(family_name, files_verified, files_failed, errors)`.
- State persisted at `<data_root>/_system/purity/backup/local_state.json`
  (parallel to existing `heartbeats/`, `audit/`, `pulse/` convention),
  written via `write_json_atomic`.

### Catalog (P1 scope, per P0 §1 "Restore-required backup source catalog")
```text
INCLUDE:
  1. Notes:            <repo>/purity_app/notes/PurityApp/default/*.jsonl
  2. Bible library:     <data_root>/bible_library.json
  3. Bible memorizing:  <data_root>/bible_memorizing.json
  4. Prayer recipients: <data_root>/data/prayer_recipients.json
  5. Prayer prayed:     <data_root>/data/prayer_prayed.json
  6. Tag library:       <repo>/purity_app/data/tags.json
  7. Reminders override:<data_root>/reminders.yaml            (only if present)
  8. User preferences:  %LOCALAPPDATA%\purity_app\settings.yaml (optional)

EXCLUDE:
  Guided check-ins (no durable store — product gap, not backup's fault)
  System event journal, pulse cadence state, panic stats, url history
  Heartbeats, watchdog audit log, debug logs, QSettings registry entries
```

### Implementation sequence
1. `models.py` — result/enum dataclasses (no I/O).
2. `catalog.py` — `PurityBackupCatalog.discover()`, unit-testable against
   `tmp_path` fixtures that stand in for `data_root`/repo paths.
3. `destinations/local.py` — `LocalFilesystemDestination` wrapping
   `copy_file_verified()` per file, deterministic destination layout
   (mirror-style: `<destination_root>/<family_name>/<relative_path>`).
4. `state.py` — load/save `BackupRunResult` history via
   `write_json_atomic`.
5. `service.py` — `BackupService.run()` orchestrates 2–4, records result,
   never raises past its own boundary (report traceback, return a FAILED
   result instead).
6. `settings_schemas.py` — add `backup_local_destination` setting.
7. Tests (see below).
8. Manual Windows smoke: point at a real secondary path, run once, inspect
   destination + state file by hand.

### Safety constraints
- COPY_ONLY — never delete or move source files.
- Missing/unavailable destination fails visibly (raised/returned FAILED
  status), no silent fallback to another location.
- An unverified copy is never recorded as VERIFIED.
- Re-running the same backup against the same destination is idempotent
  (identical files short-circuit via `copy_file_verified`'s
  `ALREADY_PRESENT_IDENTICAL` outcome).
- Destination-conflict and source-changed-during-copy outcomes from
  `copy_file_verified` are surfaced in `FamilyResult`, not swallowed.
- Torn-file reads on `BibleLibrary`/`TagLibrary` are handled by a single
  bounded retry-on-hash-mismatch in `BackupService`, not by changing the
  source writers.
- No recursive self-backup: destination path must not resolve inside any
  source family path (validated before running).

### Non-goals (P1)
- Qt/tray integration (P2).
- Scheduling (P3).
- Dropbox (P4).
- Any restore/mutation of source data.
- `StorageRegistry`/`StorageProfile` machinery — use a plain destination
  `Path` unless implementation reveals a concrete need for the registry.

### Tests
```text
tests/backup/test_catalog.py   — resolves expected paths against tmp_path fixtures,
                                  including the reminders.yaml "only if present" case
tests/backup/test_service.py   — full run against tmp_path source/dest roots using
                                  the real copy_file_verified primitive; covers
                                  idempotent re-run, missing destination,
                                  identical-file short-circuit, conflict case
tests/backup/test_state.py     — run-history persistence round-trip
```

### Acceptance criteria
```text
[ ] All restore-required families included; guided check-ins explicitly excluded/documented.
[ ] Manual secondary-drive backup succeeds end-to-end.
[ ] Every copied file verified (size + SHA-256 source vs destination).
[ ] Source files untouched (no deletion/mutation).
[ ] Re-run is safe/idempotent.
[ ] Missing destination fails visibly, no silent fallback.
[ ] Unit/integration tests pass using temporary roots.
[ ] Windows smoke run against a real secondary path passes.
```

### Stop/review gate
Stop after P1 for review before starting P2. Do not begin tray/Qt work
until P1's catalog, destination layout, and state schema are confirmed
against real repository behavior.

---

## P2 — Tray + Backup dialog + background worker integration — PLANNED

### Objective
Wire the P1 `BackupService` into the running `app.py` process: a "Backup..."
tray action, a compact summary in the existing Status window, a dedicated
Backup dialog, and a background worker thread so the GUI never blocks.

### Existing infrastructure reused
- `shane_common.watchdog.tray.base_tray_app.BaseTrayApp` (already backs
  `PurityTrayApp`) — add one new `QAction`.
- `shane_common.watchdog.tray.base_window.BaseStatusWindow` — base class
  for the new `BackupDialog`, same pattern as `PurityStatusWindow`.
- The P1 `BackupService` — called as-is, unmodified.

### Files/modules likely added or modified
```text
purity_app/ui/backup/backup_dialog.py           # NEW — BackupDialog(BaseStatusWindow)
purity_app/services/backup/lock.py              # NEW — Purity-local single-flight lock
purity_app/ui/system/supervisor_tray.py         # add "Backup..." QAction + handler
purity_app/app.py                               # instantiate BackupService/worker,
                                                 # wire tray callback (~ near existing
                                                 # PurityTrayApp construction)
```

### Important contracts/classes/functions
- `BackupWorker(QThread)` (or `QRunnable`+`QThreadPool`) — runs
  `BackupService.run()` off the GUI thread, emits a signal with
  `BackupRunResult` on completion.
- `BackupController` — thin glue owned by `app.py`; exposes
  `back_up_now()` used by both the tray action and the dialog button;
  acquires the single-flight lock before starting the worker.
- `SingleFlightLock` (Purity-local, `services/backup/lock.py`) — prevents
  overlapping manual runs (scheduling arrives in P3 and reuses the same
  lock).

### Implementation sequence
1. Read the current state of `purity_app/ui/system/supervisor_tray.py` and
   `app.py`'s tray construction point before editing — do not assume line
   numbers from the P0 audit are still accurate.
2. `lock.py` — minimal file/in-memory lock sufficient for one process.
3. `BackupWorker` + `BackupController` in `app.py`'s existing wiring.
4. Add `Backup...` tray action calling `BackupController.back_up_now()`.
5. Add compact LOCAL/DROPBOX/last-success/next-run block to
   `PurityStatusWindow.refresh()` (DROPBOX/next-run show placeholder state
   until P3/P4 exist).
6. `BackupDialog` — protected-data list, local backup status, `Back Up Now`
   / `Verify` / `Choose Local Destination` buttons, delegating everything
   to `BackupController`/`BackupService`.

### Safety constraints
- No file/hash/network calls inside any Qt slot — always delegate through
  `BackupController`.
- Single-flight lock must prevent a second manual click from starting a
  concurrent run while one is in progress.
- Backup failures must never crash `app.py` or affect its heartbeat.

### Non-goals (P2)
- Scheduling (P3).
- Dropbox (P4).
- Restore functionality (P6).

### Tests
```text
tests/backup/test_lock.py             — single-flight behavior under overlapping calls
tests/ui/test_backup_dialog.py        — real-QApplication smoke test, mirroring
                                          existing NoteDialog/BibleBrowserDialog tests
```

### Acceptance criteria
```text
[ ] Tray "Backup..." action opens the dialog; "Back Up Now" runs BackupService.
[ ] GUI remains responsive during a backup run.
[ ] Status window shows local backup health.
[ ] Overlapping manual triggers cannot double-run.
[ ] Watchdog/heartbeat behavior unaffected.
```

### Stop/review gate
Stop after P2 for review. Confirm the lock/worker pattern before P3 reuses
it for scheduled runs.

---

## P3 — Sunday scheduling — PLANNED

### Objective
Add a simple weekly (day/time/timezone) schedule, hosted by `app.py`'s
existing `QTimer` poll loop, that triggers exactly one `BackupService` run
per due occurrence, sharing the P2 single-flight lock with manual runs.

### Existing infrastructure reused
- `app.py`'s existing `QTimer` pattern (pulse manager/web watcher already
  use this).
- P1 `BackupService`, P2 `SingleFlightLock`.
- `shane_common.io.atomic.write_json_atomic` for due-occurrence state.

### Files/modules likely added or modified
```text
purity_app/services/backup/scheduler.py     # NEW — due-occurrence check
purity_app/app.py                            # QTimer tick wired to scheduler
purity_app/services/settings_schemas.py      # schedule enabled/day/time/timezone settings
```

### Important contracts/classes/functions
- `BackupSchedule(enabled, weekday, time, timezone)` — settings-backed.
- `ScheduleState(last_evaluated_occurrence_id, last_run_result_ref)` —
  persisted, ensures a given due occurrence executes once even across
  restarts.
- `scheduler.is_due(now, schedule, state) -> occurrence_id | None`.

### Implementation sequence
1. Re-read current `app.py` QTimer wiring and P2's `BackupController`
   before assuming the original integration point still applies.
2. Implement `scheduler.py` with pure functions (easily unit-testable,
   inject `now`).
3. Persist `ScheduleState` via `write_json_atomic`.
4. Wire a QTimer tick (reuse existing timer or add one) to call
   `scheduler.is_due()`, then `BackupController.back_up_now()` through the
   same single-flight lock as manual runs.
5. Add schedule settings to the Backup dialog (P2's dialog, minor addition).

### Safety constraints
- Exactly-once execution per due occurrence, durable across restarts.
- Disabled schedule never runs.
- Manual and scheduled paths share the same lock and same `BackupService`.

### Non-goals (P3)
- Windows Task Scheduler (only if evidence proves `app.py` cannot satisfy
  the requirement — not expected).
- Dropbox (P4).

### Tests
```text
tests/backup/test_scheduler.py   — due-occurrence computation, restart-safety,
                                     disabled-schedule no-op, timezone/DST edge cases
```

### Acceptance criteria
```text
[ ] Schedule configurable (enabled/day/time/timezone).
[ ] Due occurrence runs exactly once.
[ ] Restart does not duplicate a completed occurrence.
[ ] Disabled schedule does not run.
[ ] Manual backup still available and uses the same lock/service.
```

### Stop/review gate
Stop after P3 for review before introducing Dropbox and its credential
requirements.

---

## P4 — Dropbox backup — PLANNED

### Objective
Add Dropbox as a second, independent backup destination behind a shared
`BackupDestination` interface, with its own verification state and its own
failure isolation from local backup.

### Existing infrastructure reused
- P1 `BackupService`/catalog (destination-agnostic core).
- P2/P3 controller, worker, lock, schedule (Dropbox reuses the same
  schedule tick and same lock domain, but its own run/verification state).

### Files/modules likely added or modified
```text
purity_app/services/backup/destinations/dropbox.py   # NEW — DropboxDestination
purity_app/services/backup/credentials.py             # NEW — secure token storage
purity_app/services/backup/service.py                  # extend to support multiple destinations
purity_app/services/backup/state.py                    # independent DROPBOX state block
purity_app/ui/backup/backup_dialog.py                  # add Dropbox section
```

### Required repository discovery before changing code
- Confirm no `dropbox` dependency or Dropbox references exist yet
  (P0 already confirmed this — re-verify, do not assume it is still true).
- Confirm current P1–P3 destination interface shape before designing
  `BackupDestination` — do not guess it from this plan alone.

### Important contracts/classes/functions
- `BackupDestination` (protocol/ABC): `put(file) -> DestinationOutcome`,
  `verify(file) -> DestinationOutcome`.
- `DropboxDestination(BackupDestination)` — OAuth refresh-token auth,
  content-hash verification using Dropbox's own hash algorithm (not
  SHA-256 reuse).
- Credential storage: Windows Credential Manager via `keyring`, or DPAPI
  via `ctypes` — decide and document the choice at implementation start;
  **stop before implementation if this is unresolved.**

### Safety constraints
- Never store Dropbox tokens in plaintext `settings.yaml` or ordinary
  `QSettings`.
- Dropbox failure must never affect local backup state or normal Purity
  operation.
- Local and Dropbox state persisted independently.
- Remote verification uses Dropbox-supported content/revision semantics,
  not assumed SHA-256 equivalence.

### Non-goals (P4)
- Restore UI (P6).
- Reliability hardening beyond what's needed for a working Dropbox path (P5).

### Tests
```text
tests/backup/test_dropbox_destination.py   — mocked Dropbox API, upload/verify/conflict
tests/backup/test_credentials.py           — token storage/retrieval round-trip
```

### Acceptance criteria
```text
[ ] Dropbox and local state persisted independently.
[ ] Dropbox outage does not affect Purity operation.
[ ] Credentials stored securely, outside source control.
[ ] Retry is idempotent; conflicts fail visibly.
[ ] Harmless restore/download smoke documented.
```

### Stop/review gate
**Explicit stop-before-implementation gate:** do not write Dropbox
integration code until credential storage approach is decided and
approved.

---

## P4.5 — DPAPI secret store migration (replace keyring/Credential Manager) — NEXT

### Objective
P4's Dropbox credential storage (`keyring` → `WinVaultKeyring` → Windows
Credential Manager) is unusable on this machine: both Python `keyring` and
native `cmdkey /generic:...` fail identically through `CredWrite` with
`ERROR_NOT_ENOUGH_MEMORY`. This was fully diagnosed in a prior session
(native `cmdkey` reproduction with no Python/keyring/pywin32 involved,
~291 existing vault entries as the known trigger, disk space and `VaultSvc`
ruled out) — that investigation is not reopened here. This phase
permanently replaces Credential Manager with a reusable Windows DPAPI
(`CryptProtectData`/`CryptUnprotectData`, current-user scope) secret store,
refactors Dropbox credential handling onto it exclusively, and removes
`keyring` from the codebase. Designed as reusable infrastructure (not a
Dropbox-only hack) since the Trading App is expected to need the same
mechanism later.

### Decisions carried in from the handoff (not re-litigated during implementation)
- Do NOT preserve `keyring` as a primary store or fallback.
- Do NOT invent a master password, persist a custom encryption key, fall
  back to plaintext, use `.env` for runtime secrets, store secrets in
  ordinary settings/source/unencrypted Registry, or log secret values.
- Do NOT repair Windows Credential Manager, enumerate/delete stale
  Credential Manager entries, or migrate old keyring secrets — no
  production Dropbox credential exists yet to preserve; the new store
  simply becomes authoritative from first use.
- Diagnostic/workaround code temporarily added to
  `services/backup/credentials.py` during troubleshooting
  (`_configure_windows_persistence()`, delete-before-write in `_set()`,
  `print(...)`/`traceback.print_exc()` diagnostics) is deleted entirely,
  not ported or referenced.

### Required repository discovery before changing code
- Confirm `purity_app`'s existing clean dependency on `shane_common` (e.g.
  `copy_file_verified` already used by `services/backup/destinations/local.py`)
  still holds, and whether `shane_common`'s conventions support a new
  `shane_common/security/` module before placing the abstraction there. If
  premature, implement Purity-local instead, structured so it can move
  later without changing callers.
- Confirm exactly what the installed Dropbox SDK / current OAuth
  no-redirect flow actually requires — determine whether `app_secret` is
  still necessary given a PKCE-capable authorization-code + offline-access
  flow, rather than assuming the P4 shape must be preserved as-is.
- Confirm `keyring` usage is still isolated to exactly
  `services/backup/credentials.py` and `tests/backup/test_credentials.py`
  before removing it (P4's progress log claims this; re-verify).
- Confirm Purity's canonical per-user state directory conventions
  (`%LOCALAPPDATA%\...`) before choosing the secrets file location, rather
  than inventing a new root ad hoc.

### Files/modules likely added or modified
```text
shane_common/security/secret_store.py          # NEW (if placement confirmed) — SecretStore ABC/protocol
shane_common/security/windows_dpapi_store.py   # NEW (if placement confirmed) — DPAPI-backed implementation
  # (or Purity-local equivalents under purity_app/services/security/ if shared placement is premature)
purity_app/services/backup/credentials.py       # refactor onto SecretStore, delete diagnostic code
purity_app/services/backup/dropbox_auth.py      # drop app_secret persistence if PKCE removes the need
purity_app/services/backup/destinations/dropbox.py
purity_app/services/backup/dropbox_service.py
purity_app/services/backup/dropbox_controller.py
purity_app/services/backup/models.py
purity_app/services/backup/state.py
purity_app/ui/backup/backup_dialog.py           # update storage-mechanism text/status if needed
purity_app/services/settings_schemas.py         # app_key stays ordinary settings; drop app_secret setting if removed
purity_app/tests/backup/test_credentials.py     # replaced by SecretStore tests
purity_app/tests/backup/test_secret_store.py    # NEW
pyproject.toml / requirements (Purity + shane_common as applicable)  # remove keyring dependency
```

### Important contracts/classes/functions
- `SecretStore` (generic abstraction):
  `set_secret(namespace, name, value) -> None`,
  `get_secret(namespace, name) -> str | None`,
  `delete_secret(namespace, name) -> None`.
- `WindowsDpapiSecretStore(SecretStore)` — DPAPI current-user encrypt/decrypt
  via `ctypes` (`CryptProtectData`/`CryptUnprotectData`), backed by an
  application-owned encrypted file (e.g.
  `%LOCALAPPDATA%\ShaneApps\purity_app\secrets.dat`, or Purity's existing
  canonical per-user state root if one already exists), atomic writes,
  explicit corruption/decrypt-failure errors (no silent fallback), namespace
  isolation, overwrite and delete support, restricted file ACLs to the
  current Windows user where practical.
- Namespace convention: `purity_app.dropbox` / `refresh_token` (mirrors the
  handoff's `trading_app.kraken` / `trading_app.telegram` examples for
  future reuse).
- Persisted Dropbox configuration after this phase:
  `app_key` → ordinary settings; `refresh_token` → `SecretStore`;
  `app_secret` → removed if the PKCE-capable flow makes it unnecessary
  (confirmed against the actual Dropbox SDK/flow, not assumed).

### Safety constraints
- Encrypted DPAPI payloads only; current-user protection; never plaintext,
  never a custom/persisted encryption key, never logged secret values.
- Dropbox auth failures continue to leave local backup state completely
  unaffected (existing P4 isolation guarantee preserved).
- Existing `DropboxAuthState` behavior (`DISABLED` / `AUTH_REQUIRED` /
  `READY` / `REAUTH_REQUIRED`) preserved exactly — only the underlying
  storage mechanism changes.
- No repo-local secret storage; no secrets in source, ordinary settings,
  backup state JSON, manifests, audit logs, or the local/Dropbox backup
  trees themselves.

### Non-goals (P4.5)
- Repairing or cleaning Windows Credential Manager.
- Migrating any old keyring-stored secrets.
- Cloud secret managers, BitLocker-specific behavior, cross-platform
  support beyond what falls out naturally from DPAPI being Windows-only.
- Redesigning the Dropbox backup destination, local backup, or scheduler
  architecture beyond the credential-storage swap.

### Environment follow-up (from this session, to resolve explicitly, not left ambiguous)
- Both venvs (`D:\code\git\.venv` used to launch the app,
  `D:\code_new\trading_root\.venv`/`D:\code\git_new\trading_root\.venv`
  used for `pytest`) currently have `pywin32` installed and
  `pywin32-ctypes` uninstalled from prior troubleshooting. Once `keyring`
  is removed, explicitly decide whether `pywin32` (and any other
  now-unused packages) should also be removed from both venvs, and apply
  the same decision to both — do not leave them in a mismatched or
  accidental state.

### Tests
```text
tests/backup/test_secret_store.py — set/read, overwrite, delete, missing
    secret, namespace isolation, corrupt encrypted payload, DPAPI decrypt
    failure, atomic persistence, proof the persisted file does not contain
    the literal secret value (byte-content assertion, not just "looks
    encrypted")
tests/backup/test_dropbox_service.py (extended) — auth state with missing
    refresh token, auth state with valid refresh token, Dropbox auth
    failure does not affect local backup state
```

### Acceptance criteria
```text
[ ] Generic SecretStore implemented and placed per confirmed dependency
    direction (shane_common or Purity-local), with a documented reason.
[ ] Dropbox credential handling refactored onto SecretStore exclusively;
    keyring usage removed from services/backup/credentials.py.
[ ] Diagnostic/workaround code from troubleshooting deleted, not ported.
[ ] keyring dependency removed from project dependencies if nothing else
    uses it; pywin32/pywin32-ctypes decision made explicitly for both venvs.
[ ] app_secret persistence removed if confirmed unnecessary under PKCE,
    otherwise explicitly justified if retained.
[ ] DropboxAuthState values (DISABLED/AUTH_REQUIRED/READY/REAUTH_REQUIRED)
    behave identically to before.
[ ] Local/Dropbox backup isolation preserved (Dropbox failure never
    affects local backup state).
[ ] Backup dialog text/status accurately reflects the new storage
    mechanism.
[ ] Tests above added and passing; no unrelated regressions in the full
    purity_app suite.
[ ] Encrypted secrets file location, persisted Dropbox fields, and
    keyring-removal status all documented in the completion report.
```

### Stop/review gate
Stop after P4.5 for review before returning to P5 (reliability hardening),
since P5 assumes a stable, final credential-storage mechanism to harden
against.

---

## P5 — Reliability hardening — PLANNED

### Objective
Harden the now-working local + Dropbox implementation based on actual
observed failure modes, not speculative ones.

### Scope (only what implementation evidence justifies)
- Single-flight robustness (edge cases found in P2/P3 usage).
- Source-change handling refinement.
- Destination-conflict handling refinement.
- Retry policy tuning.
- Interrupted-run recovery.
- Stale-backup detection (e.g., no successful run in N days).
- Operator notification (tray/status surfacing of failures).
- Independent local/cloud failure state confirmed under real failures.

### Required repository discovery before changing code
Read P1–P4 completion evidence/progress log first; do not assume gaps
exist that were already closed.

### Non-goals (P5)
Do not build a generalized backup framework beyond what P1–P4 already
require in practice.

### Tests
Targeted regression tests for whatever concrete failure modes are
addressed.

### Acceptance criteria
Defined once P1–P4 evidence identifies concrete gaps; no acceptance
criteria are frozen here in advance.

### Stop/review gate
Stop after P5 for review before final restore-proof phase.

---

## P6 — Restore proof — PLANNED

### Objective
Prove that a completed backup can actually restore usable data, without
adding a destructive in-place restore feature.

### Scope
- Restore a selected backup run into a temporary verification root.
- Verify hashes/expected files for every restore-required family.
- Open/read representative data from each family (notes, Bible library,
  prayer recipients, tags, etc.).
- Document the restore procedure.
- Record successful restore verification (durable evidence, e.g. a dated
  restore-verification report).

### Files/modules likely added or modified
```text
purity_app/services/backup/restore.py        # NEW — restore-to-temp-root only
purity_app/tests/backup/test_restore.py
```

### Non-goals (P6)
- No in-place destructive Restore button.
- No production restore workflow beyond the temp-root verification.

### Tests
```text
tests/backup/test_restore.py   — restore a real backup run to tmp_path, verify
                                   hashes and representative content per family
```

### Acceptance criteria
```text
[ ] Restore-to-temp-root succeeds for a real backup run.
[ ] Every restore-required family verified for hash + representative content.
[ ] Restore procedure documented.
[ ] Restore verification recorded.
```

### Stop/review gate
Final phase — stop for review; no further phases follow automatically.

---

## Progress logging recommendation

As implementation proceeds, maintain a compact progress log at:

```text
D:\code\git_new\purity_app\docs\03_ACTIVE_WORK\2026-09-15_Purity_App_Backup_Progress_Log_v1_0.md
```

Not created now — create only when P1 implementation actually begins, and
use it as the compact current-state handoff between phase chats.
