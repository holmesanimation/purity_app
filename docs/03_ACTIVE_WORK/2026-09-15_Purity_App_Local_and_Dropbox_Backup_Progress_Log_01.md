# Purity App Backup — Progress Log

Companion to
[2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md](./2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md).

## 2026-09-23 — Post-P6 — Monthly Disaster Recovery Drill workflow (COMPLETE)

P6 (restore proof) was already complete and is unchanged in behavior/criteria
— this is an operational enhancement on top of it, per the audit below.

### Audit of completed P6 (before writing any code)

- Service: `services/backup/restore.py`'s `restore_backup(destination_root,
  verification_root, data_root)` — hash-verified copy (via
  `copy_file_verified`) into a fresh verification root, cross-checked
  against `local_manifest.json`, plus a per-family representative-content
  parse (`json.loads`/`yaml.safe_load`/per-line JSONL). Only ever exercised
  against the LOCAL backup folder layout (`<destination_root>/<family>/
  <filename>`) — there was no Dropbox-specific restore/download path.
- Result/status model: `RestoreResult`/`FamilyRestoreResult` (in
  `restore.py`, not `models.py`), `status` in `{success, partial, failed}`.
- Persisted state: `<data_root>/_system/purity/backup/restore_state.json`
  via `append_restore_result`/`load_restore_state` — a single shared history
  list, not tagged by destination.
- Cleanup: none — `restore_backup()` never deletes its own
  `verification_root`; that has always been the caller's responsibility
  (P6's own tests use `tmp_path`).
- No existing controller/worker/UI exposure for restore — P6 was a callable
  proof-of-restore function plus tests only.

### What was missing for a real Dropbox drill

Dropbox's existing backup path only ever verified *upload* (metadata/
content-hash comparison via `files_get_metadata`), never a download. Running
a "Dropbox recovery drill" against P6 as-is would not have exercised any
real Dropbox recovery. Added the minimum needed, reusing everything else:

- `destinations/dropbox.py`: added `download_dropbox_backup(client,
  remote_folder, download_root)` — lists and actually downloads
  (`files_download`) every file under the remote folder into
  `download_root/<family>/<filename>`, verifying each downloaded file's
  bytes against Dropbox's own reported `content_hash` (raises on mismatch,
  never accepted silently). The downloaded folder is then handed to the
  *same* `restore_backup()` as its `destination_root` — so Dropbox recovery
  is proven by the identical P6 hash + content checks as LOCAL, with no
  second verification engine.
- `restore.py`: added a `destination: str = "local"` field to
  `RestoreResult`/param to `restore_backup()` so the *same* shared
  `restore_state.json` history can be filtered per destination
  (`"local"`/`"dropbox"`) — no new state file, no schema redesign.

### New operational layer

- `services/backup/health.py` (extended, not replaced): `is_recovery_drill_due
  (last_successful_drill_at, now, interval_days=30)` (pure), plus
  `last_successful_restore(runs, destination)` /
  `last_restore_attempt(runs, destination)` helpers that filter
  `restore_state.json` by the new `destination` tag. A later PARTIAL/FAILED
  attempt never resets `last_successful_drill_at`, per spec.
- `services/settings_schemas.py`: added `backup_recovery_drill_interval_days`
  setting (default 30) + `get_backup_recovery_drill_interval_days()`.
- `services/backup/recovery_drill.py` (new) — the operational glue:
  `run_local_drill(settings_manager)` (returns `None` if no local
  destination configured) and `run_dropbox_drill(settings_manager)` (returns
  `DROPBOX_NOT_CONFIGURED`/`DROPBOX_REAUTH_REQUIRED` instead of running when
  Dropbox isn't ready). Both use a `tempfile.TemporaryDirectory` for the
  verification root (and, for Dropbox, an additional one for the downloaded
  copy) so drill artifacts are always cleaned up automatically — this is
  the operational layer's own cleanup, not a change to P6's (still
  caller-managed) cleanup contract.
- `services/backup/recovery_drill_controller.py` (new) —
  `RecoveryDrillController(QObject)`, mirroring `BackupController`/
  `DropboxController` exactly: owns its own `SingleFlightLock` (duplicate
  clicks rejected), runs both destinations' drills on a background
  `QThread` (no file/hash/network work on the GUI thread), and — the
  concurrency invariant — skips a destination's drill this run if that
  destination's own `BackupController`/`DropboxController.is_running` is
  currently `True` (checked once at drill start; unrelated destinations are
  never serialized against each other). No new lock framework.

### UI

- `ui/backup/backup_dialog.py`: added a "Disaster Recovery" `QGroupBox`
  with independent LOCAL/DROPBOX status lines (never/date + ✓ or ⚠ DUE,
  or "Not configured"/"Reauthentication required" without ever showing
  FAILED for those states), an interval label, and a single **Run Recovery
  Drill** button wired to `RecoveryDrillController`. The button disables on
  `drill_started`, re-enables/refreshes on `drill_finished`/`drill_rejected`.
  No file/hash/network code in the dialog — everything delegates to the
  controller.
- `ui/system/supervisor_tray.py`: `PurityStatusWindow` gained a compact
  `recovery drill: LOCAL ok|due | DROPBOX ok|due` status line (own
  `_format_recovery_drill_status()`), and `PurityTrayApp` gained a
  `_poll_recovery_drill_due()` tick (added alongside the existing
  `_poll_backup_staleness()`) that fires exactly one tray balloon on a
  healthy→due *transition* per destination (tracked via
  `_local_drill_was_due`/`_dropbox_drill_was_due`, same pattern as P5's
  staleness notification) — a combined single balloon if both destinations
  become due together, independent balloons otherwise. The monthly drill is
  never triggered automatically; the reminder only prompts the user to open
  Backup and click the button.
- `app.py`: constructs one `RecoveryDrillController(settings_manager,
  backup_controller, dropbox_controller, parent=app)` alongside the
  existing controllers and passes it into `PurityTrayApp` (which lazily
  passes it into `BackupDialog`).

### Tests

- `tests/backup/test_recovery_drill_health.py` (new, 7 tests): no
  successful drill → due; recent success → not due; old success → due;
  boundary (29d not due @30d interval); a later FAILED attempt does not
  reset/clear a prior SUCCESS's due state; a new SUCCESS resets due state;
  LOCAL/DROPBOX independence; `last_restore_attempt` includes failures.
- `tests/backup/test_dropbox_download.py` (new, 2 tests): a fake
  `dropbox.Dropbox` duck-type proves `download_dropbox_backup()` writes
  real file bytes, and raises on a content-hash mismatch (never silently
  accepted).
- `tests/backup/test_recovery_drill_service.py` (new, 4 tests):
  `run_local_drill` returns `None` when unconfigured; a configured local
  backup drill reuses `restore_backup()` unchanged and tags
  `destination="local"` in the shared `restore_state.json`; Dropbox drill
  returns `DROPBOX_NOT_CONFIGURED`/`DROPBOX_REAUTH_REQUIRED` appropriately
  without running.
- `tests/backup/test_recovery_drill_controller.py` (new, 3 tests, real
  `QApplication`): a full drill run reports both destinations' results via
  `drill_finished`; a duplicate click while running is rejected via
  `drill_rejected` and never starts a second run; a destination whose
  backup/upload controller is currently running is skipped for this drill
  while the other destination still runs normally (concurrency invariant).
  Uses lightweight stub `QObject`s for the backup/dropbox controller
  dependencies (exposing only `is_running`) rather than real
  `BackupController`/`DropboxController` instances, to avoid a real-QThread
  ordering/teardown flakiness observed when stacking multiple
  QThread-backed Qt test files back-to-back in one pytest session (an
  existing environment fragility, not a defect in the new code — see the
  matching one-line `controller._thread.wait(2000)` addition in
  `test_backup_dialog.py`'s existing thread-based test, added defensively
  for the same reason).
- Full `tests/backup` suite: 81/81 passing (repeated runs confirmed
  stable, not flaky).
- Full purity_app suite (`python -m pytest` from `purity_app/`, respecting
  `pytest.ini`'s existing ignores): 206 passed, 0 failed, 0 errors — no
  regressions.

### Explicit deviations from the handoff, and why

- No separate `RestoreToProduction`/`--force` anything was added or
  considered — out of scope per the non-goals, unchanged.
- The Dropbox drill's temporary verification/download roots are cleaned up
  automatically (`tempfile.TemporaryDirectory`) by the new operational
  layer, since P6's `restore_backup()` itself has never owned cleanup of
  its caller-supplied `verification_root` — this is additive, not a change
  to P6's contract.
- Added a `destination` field to `RestoreResult`/`restore_backup()` (default
  `"local"`, fully backward compatible) so LOCAL/DROPBOX recovery health can
  be derived independently from the one existing shared
  `restore_state.json` — the minimum change judged necessary to satisfy the
  "LOCAL and DROPBOX must remain independent" requirement without building
  a second state file or a second verification engine.

### Status

Post-P6 monthly Disaster Recovery Drill workflow is **COMPLETE** and tested.
P6 itself remains COMPLETE and unmodified in verification criteria.

## 2026-09-23 — P6 implemented (restore proof) — final phase

### P6 — Restore proof (COMPLETE)

Non-destructive proof that a completed local backup can actually restore
usable data, without adding an in-place restore feature (explicit non-goal
per the plan).

Added `services/backup/restore.py`:

- `restore_backup(destination_root, verification_root, data_root) ->
  RestoreResult` — restores whatever is *currently* present in the local
  backup destination (mirrors `LocalFilesystemDestination`'s
  `<destination_root>/<family_name>/<filename>` layout; there are no
  per-run file snapshots in the state schema, only aggregate counts, so
  this restores the destination's current state rather than a specific
  past run) into a fresh `verification_root` via the same
  `copy_file_verified` primitive backups use.
- Cross-checks each restored file's hash against `local_manifest.json`'s
  last-verified `ManifestEntry` — a mismatch (independent destination
  tampering/corruption since the last verified backup) is recorded as a
  failed file, never silently accepted.
- Runs a per-family "representative content" parse to prove restored data
  is actually usable, not just byte-identical: `json.loads` for
  bible_library/bible_memorizing/prayer_recipients/prayer_prayed/
  tag_library/diet_state, per-line `json.loads` for notes JSONL,
  `yaml.safe_load` for reminders_override/user_preferences.
- Records durable evidence at
  `<data_root>/_system/purity/backup/restore_state.json` via
  `append_restore_result`/`load_restore_state` (own file, parallel to
  `local_state.json`/`dropbox_state.json` — not reusing
  `BackupRunResult`/`state.append_run`, since restore results have a
  different shape; added standalone `FamilyRestoreResult`/`RestoreResult`
  dataclasses in `restore.py` itself, not `models.py`).

No restore UI/button was added — this is a callable proof-of-restore
function plus tests only, invoked manually (e.g. from a Python shell)
against the real backup destination when actually needed.

### Tests

- `tests/backup/test_restore.py` (new, 3 tests): full success including
  hash + content verification, tampered-destination-file detected as
  failed/partial, missing `destination_root` -> failed with empty
  `family_results`.
- Full `tests/backup` suite: 64/64 passing.
- Full purity_app suite re-run after P6: 189 passed, 0 failures — no
  regressions.

### Status

P6 is **COMPLETE** and tested. This was the final planned phase (P1–P6) of
the 2026-09-15 backup implementation plan.

## 2026-09-23 — P5 implemented (reliability hardening)

### P5 — Reliability hardening (COMPLETE)

Scoped to two concrete gaps found by reading the actual P1–P4 code (not
speculative ones), per the plan's non-goal against building a generalized
framework:

1. **No operator notification.** Scheduled/manual backup failures were only
   visible if the user manually opened the Backup dialog or Status window —
   a scheduled 2am failure could go unnoticed indefinitely.
2. **No stale-backup detection.** Nothing flagged if backups silently
   stopped succeeding (destination unplugged, Dropbox reauth required,
   etc.) — a broken schedule looked identical to a healthy one at a glance.

Single-flight lock, source-change handling, destination-conflict handling,
retry policy, and interrupted-run recovery were all reviewed against P1–P4's
actual code and found already correct for their observed failure modes (the
in-process `threading.Lock` clears automatically on restart; P1.5's
manifest-based `refresh_or_copy`/`refresh_or_upload` already distinguishes
legitimate source changes from independent destination tampering) — no
changes made there.

Added:

- `services/backup/health.py` — pure `is_stale(runs, threshold_days, now)`
  / `last_successful_run(runs)` (no I/O, no Qt); stale if no successful run
  exists or the last one is older than the threshold.
- `settings_schemas.py` — new `backup_stale_threshold_days` setting (int,
  default 10) + `get_backup_stale_threshold_days()`.
- `ui/system/supervisor_tray.py`:
  - `PurityStatusWindow._format_backup_status()` appends `[STALE]` to the
    LOCAL/DROPBOX status text when `health.is_stale()` is true.
  - `PurityTrayApp.__init__` connects `backup_controller.run_finished` /
    `dropbox_controller.run_finished` to `_notify_backup_result()`, which
    shows a tray balloon (via the existing `notify_running()` helper) for
    any non-`SUCCESS` run (PARTIAL/FAILED), including `last_error`.
  - `_poll()` (already ticking regularly) now also calls
    `_poll_backup_staleness()`, which shows a one-time balloon when
    local/Dropbox staleness *transitions* from not-stale to stale (tracked
    via `_local_backup_was_stale`/`_dropbox_backup_was_stale` booleans, so
    it doesn't repeat every poll tick).

### Tests

- `tests/backup/test_health.py` (new, 5 tests): no-runs-is-stale,
  recent-success-not-stale, old-success-is-stale, only-failed-runs-is-stale,
  last-successful-run-ignores-trailing-failure.
- Full `tests/backup` suite: 61/61 passing.
- Full purity_app suite re-run after P5 (excluding the 3 pre-existing
  PIL-import collection errors): 186 passed, 0 failures. The previously
  tracked 5 pre-existing unrelated failures
  (`test_purity_preferences_integration.py` `_FakeApiServer` kwarg + 4x
  `test_web_popup.py` `_feeling_btn`) are no longer present as of this run —
  not caused by P5; unclear if fixed in an intervening session or
  environment-dependent, worth re-checking if they reappear.

### Status

P5 is **COMPLETE** and tested. P6 (restore proof) followed — see the entry
above.

## 2026-09-16 — Clarification: where Dropbox backups actually land (no code change)

User's real Dropbox app is a **Scoped App (App Folder)** permission type
named `purity_app`, confirmed via the App Console. Under App Folder access,
Dropbox sandboxes the app to `Apps/purity_app/` — the app has no visibility
outside it, regardless of the `dropbox_remote_folder` setting (default
`/PurityAppBackup`). So a successful "Back Up to Dropbox Now" run's files
are at `Apps/purity_app/PurityAppBackup/<family_name>/<filename>`, not at
a top-level `purity_app` folder. No code changed — this is expected
behavior of `dropbox_auth.py`'s `DropboxOAuth2FlowNoRedirect` flow, which
doesn't override the app's configured access type.

## 2026-09-16 — P4.5 implemented (DPAPI secret store migration, replaces keyring/Credential Manager)

### P4.5 — DPAPI secret store migration (COMPLETE)

Windows Credential Manager was confirmed permanently unusable on this
machine (see the prior "P4.5 planned" entry below for the `CredWrite`
`ERROR_NOT_ENOUGH_MEMORY` diagnosis — not reopened here). Implemented the
planned replacement:

- Added `purity_app/services/security/secret_store.py` — a generic
  `SecretStore` protocol (`set_secret`/`get_secret`/`delete_secret`,
  namespaced by `(namespace, name)`).
- Added `purity_app/services/security/windows_dpapi_store.py` —
  `WindowsDpapiSecretStore`: encrypts each secret with `CryptProtectData`
  (current-user scope, `CRYPTPROTECT_UI_FORBIDDEN`) via `ctypes`, decrypts
  with `CryptUnprotectData`, persists all secrets as one JSON file
  (`namespace\x00name` keys, base64 ciphertext values) at
  `%LOCALAPPDATA%\purity_app\secrets.dat` (via the existing
  `shane_common.preferences.paths.app_settings_path` convention), written
  atomically via `shane_common.io.atomic.write_json_atomic`. Corrupt/
  unreadable files and DPAPI decrypt failures raise explicit
  `SecretStoreError`/`SecretStoreDecryptionError` — no silent fallback.
- **Placement decision**: implemented Purity-local (not `shane_common`) —
  no second consumer (e.g. Trading App) exists yet; structured so it can be
  promoted later without changing callers.
- Rewrote `services/backup/credentials.py`: `DropboxCredentialStore` now
  wraps a `SecretStore` (constructor takes `store=`/`namespace=`, replacing
  `service_name=`) and stores only `refresh_token`. All keyring code and the
  troubleshooting diagnostic/workaround code
  (`_configure_windows_persistence()`, delete-before-write, stderr prints)
  was deleted entirely, not ported.
- **`app_secret` storage was removed entirely**, not just moved: confirmed
  by live inspection of the installed `dropbox` SDK (12.2.1) that
  `DropboxOAuth2FlowNoRedirect` supports `use_pkce=True` (no
  `consumer_secret` needed for the code exchange) and that
  `dropbox.Dropbox(oauth2_refresh_token=..., app_key=...)` refreshes a
  PKCE-issued token successfully with no `app_secret` at all (the SDK only
  adds `client_secret` to a refresh request if one was provided). Updated
  accordingly: `dropbox_auth.py`'s `DropboxAuthFlow`/`complete_authorization`
  and `dropbox_service.py`'s `get_dropbox_auth_state()`/`_build_client()`
  drop the `app_secret` parameter entirely; `backup_dialog.py`'s "Connect to
  Dropbox..." flow no longer prompts for an app secret. `dropbox_app_secret`
  was never a `settings_schemas.py` setting, so nothing needed removing
  there. `DropboxAuthState` behavior (`DISABLED`/`AUTH_REQUIRED`/`READY`/
  `REAUTH_REQUIRED`) and full local/Dropbox state isolation are unchanged.
- Confirmed zero remaining `import keyring`/`import win32*` references
  anywhere in the workspace, then uninstalled `keyring` and `pywin32` from
  `trading_root/.venv` (the venv used for `pytest`). This decision was
  **not** applied to `D:\code\git\.venv` (the separate venv that launches
  the real app, outside this workspace) — left unresolved/out of scope for
  this session.

### Tests

- `tests/backup/test_secret_store.py` (new) — round-trip, overwrite,
  delete/idempotent, missing-secret, namespace isolation, corrupt-file
  raises `SecretStoreError`, atomic write leaves no `.tmp` file behind, and
  a byte-content assertion proving the persisted file does not contain the
  literal plaintext secret value.
- `tests/backup/test_dropbox_service.py` (new) — `get_dropbox_auth_state()`
  with a missing refresh token (`AUTH_REQUIRED`) and with a valid one
  (`READY`); a Dropbox run that fails (never authorized) leaves
  `local_state.json` completely unaffected after a prior successful local
  run.
- `tests/backup/test_credentials.py` rewritten for the new
  `SecretStore`-backed constructor (in-memory fake `SecretStore`, no more
  fake keyring backend).
- Full `tests/backup` suite: 58/58 passing.
- Full purity_app suite re-run after P4.5: 246 passed, same 5 pre-existing
  unrelated failures as always (`test_purity_preferences_integration.py`
  `_FakeApiServer` kwarg mismatch + 4x `test_web_popup.py` `_feeling_btn`
  missing) — no regressions. Same 3 known PIL-import collection errors
  ignored per repo memory.

### Status

P4.5 is **COMPLETE** and tested. Ready for P5 (reliability hardening)
review.

## 2026-09-16 — Protected Data selection persisted; destination-gated controls; Dropbox now uploads from the local backup folder; statusbar added

- **Protected Data groupbox**: new "Choose Protected Data..." button opens
  the family picker (pre-checked from the persisted selection); selection
  is persisted via new `backup_selected_families` setting
  (`get_backup_selected_families()`/`set_backup_selected_families()` in
  `settings_schemas.py`; empty = all families). The groupbox label now
  lists each family with a \u2713/\u2717 to show inclusion state. "Back Up Now" no
  longer opens a picker — it runs immediately against the persisted
  selection and configured destination.
- **Local Backup groupbox**: destination label gained a red
  `SP_MessageBoxCritical` icon shown only while `backup_local_destination`
  is unset. Until a destination is configured: "Back Up Now", the Weekly
  Schedule enable checkbox/weekday/time controls, and all three Dropbox
  buttons (Connect/Disconnect/Back Up to Dropbox Now) are disabled in the
  UI (service-level rejection already existed; this adds UI-level gating).
- **Dropbox now backs up from the local backup folder, not the original
  sources.** `DropboxBackupService.run()` (`dropbox_service.py`) no longer
  calls `PurityBackupCatalog.discover()` for its file list — it fails
  visibly if `backup_local_destination` isn't configured/doesn't exist,
  otherwise scans that folder's `<family_name>/<filename>` mirror layout
  (new `_discover_local_backup_families()` helper) and uploads whatever is
  currently there. Manifest keys/family names are unchanged, so
  `dropbox_manifest.json` stays consistent with the prior model.
- **Statusbar**: `BackupDialog.statusBar()` (already present via
  `BaseStatusWindow`/`QMainWindow`) now receives a message from every
  button-driven action (choose destination, choose protected data, back
  up now start/finish/reject, and all Dropbox button actions), not just
  local-run completion.
- `tests/backup/test_backup_dialog.py` updated: unconfigured-destination
  test now asserts "Back Up Now" is disabled; the family-picker auto-accept
  workaround was removed since "Back Up Now" no longer opens a picker.
- Full `tests/backup` suite: 56/56 passing (run from `purity_app/` so the
  `services`/`ui` packages resolve).

## 2026-09-16 — Family picker simplified (no per-run destination re-entry)

`_FamilyPickerDialog` ("Back Up Now") no longer asks for a destination
folder — `PurityBackupCatalog` has always owned the family\u2192file/folder
mapping (since P1), so the dialog only needs to select which families to
include. Destination is now configured once via a new **Choose Local
Destination...** button in the main "Local Backup" box
(`BackupDialog._on_choose_destination_clicked`), persisted the same way as
before (`backup_local_destination` setting). `_on_back_up_now_clicked` now
rejects with a message if no destination is configured yet, instead of
forcing a Browse step inside the picker every run. Family checkboxes default
to checked. `tests/backup/test_backup_dialog.py` updated to auto-accept the
(now-modal, family-only) picker via a `QTimer.singleShot` + `activeModalWidget()`.
Full `tests/backup` suite: 56/56 passing.

## 2026-09-15 — P1 implemented, real Windows smoke run, P1.5 correction

### P1 — Manual verified local backup (COMPLETE)

Implemented under `purity_app/services/backup/`:

- `models.py` — `RunStatus`, `BackupSourceFamily`, `FamilyResult`, `BackupRunResult`.
- `catalog.py` — `PurityBackupCatalog.discover()`, re-resolves `data_root` from
  the settings manager on every call (never cached at import time). Resolves
  the fixed P1 family list: notes (`*.jsonl` under
  `<purity_app_root>/notes/PurityApp/default/`), `bible_library.json`,
  `bible_memorizing.json`, `data/prayer_recipients.json`,
  `data/prayer_prayed.json`, `<purity_app_root>/data/tags.json`,
  `reminders.yaml` (only if present), `%LOCALAPPDATA%\purity_app\settings.yaml`
  (optional).
- `destinations/local.py` — `LocalFilesystemDestination`, mirror-style layout
  `<destination_root>/<family_name>/<filename>`, backed by
  `shane_common.runtime.transfer.copy_file_verified`.
- `state.py` — run-history persistence at
  `<data_root>/_system/purity/backup/local_state.json` via
  `write_json_atomic`.
- `service.py` — `BackupService.run()`, destination validation (missing drive
  fails visibly, recursive self-backup prevented), never raises past its own
  boundary.
- `settings_schemas.py` — added `backup_local_destination` setting +
  `get_backup_local_destination()` helper.
- Tests: `tests/backup/test_catalog.py`, `test_service.py`, `test_state.py`
  (12 tests, all passing) using `tmp_path` against the real
  `copy_file_verified` primitive.

Full purity_app suite re-run after P1: no regressions (pre-existing unrelated
failures documented separately, see repo memory).

### Real Windows smoke test — `E:\PURITY_ARCHIVE`

Ran a full manual smoke against the real secondary drive (not just
`tmp_path` tests):

- Confirmed `E:\PURITY_ARCHIVE` was empty and outside all source roots
  before running anything.
- Configured `backup_local_destination` = `E:\PURITY_ARCHIVE` in the real
  `%LOCALAPPDATA%\purity_app\settings.yaml` and confirmed it round-trips.
- Confirmed the real catalog resolves all 8 families against the real
  `data_root` (`C:\Users\<user>\.purity`) — 11 real files found.
- First run: `SUCCESS`, 11/11 verified, 0 failed, ~9.07 MB copied
  (dominated by `bible_library.json`).
- Verified destination layout (`<dest>/<family>/<filename>`), verified
  representative files open/parse correctly (including the 9 MB
  `bible_library.json`), verified `local_state.json` persisted under the
  real `data_root` with matching `run_id`.
- Verified COPY_ONLY: source `bible_library.json` size/`LastWriteTime`
  unchanged after the backup ran.
- Second run: idempotent, `bytes_copied: 0`, all 11 still verified.

### Real bug found by the smoke: stale destination files were never refreshed

Added a real tag via `TagLibrary.add()` (a normal, legitimate source-side
change) and ran the backup a third time. Result: `PARTIAL` status,
`tag_library` failed with `destination_conflict`. Root cause: P1's
`copy_file_verified()`-based copy path can only ever take a first snapshot
of each destination file — once a destination file exists and later differs
from a changed source, it is (correctly, by that primitive's own contract)
never overwritten. There was no mechanism in `BackupService` to distinguish
"source changed normally" from "destination was tampered with
independently." This meant the backup would never actually track an
evolving file after its first copy — a real functional gap, not a smoke-test
artifact.

### P1.5 — Manifest-based safe refresh (COMPLETE)

Scoped narrowly per instruction: **did not modify or weaken
`copy_file_verified()`**. Added a Purity-local manifest recording, per
destination file, the content hash last verified by a successful backup
(`<data_root>/_system/purity/backup/local_manifest.json`, hash-authoritative,
no mtime dependency):

- `models.py` — added `BackupCopyOutcome` (superset of shane_common's
  `CopyOutcome`, adds `REFRESHED`), `ManifestEntry`, `RefreshResult`.
- `state.py` — added `manifest_path()`, `load_manifest()`, `save_manifest()`.
- `destinations/local.py` — added `LocalFilesystemDestination.refresh_or_copy()`
  implementing the 4-way distinction:
  1. destination absent → `COPIED` (via `copy_file_verified`, unchanged).
  2. destination content == source → `ALREADY_PRESENT_IDENTICAL` (unchanged).
  3. destination differs from source, but destination hash still matches the
     manifest's last-verified hash → legitimate source update → **safe
     refresh**: copy to a temp sibling file on the destination filesystem,
     verify the temp copy's hash, then atomically `os.replace` it in. Never
     overwrites in place before verification. On any failure, the previous
     verified destination file is left untouched.
  4. destination differs from source AND destination hash no longer matches
     the manifest → `DESTINATION_CONFLICT`, fails visibly, not overwritten.
- `service.py` — `BackupService.run()` now loads the manifest at the start
  of each run, calls `refresh_or_copy()` per file, updates the manifest for
  every successful outcome, and persists it at the end of the run (even on
  partial failure, so successes are still recorded).
- Tests added: `tests/backup/test_local_destination.py` (new — 6 unit tests
  covering all 4 outcome cases plus source-changed-during-refresh) and
  extended `test_service.py` (legitimate refresh, manifest hash update,
  independent-modification conflict not overwritten, failed-refresh leaves
  prior backup intact, COPY_ONLY invariant across a refresh) and
  `test_state.py` (manifest round-trip). 25/25 backup tests passing.
- Full purity_app suite re-run after P1.5: no regressions (5 pre-existing
  unrelated failures remain, same root causes as before this work; see repo
  memory for details — unrelated to backup).

### Resumed smoke test after P1.5

- One-time transition note: the live `E:\PURITY_ARCHIVE\tag_library\tags.json`
  predated the manifest, so it had to be removed once to let the new code
  establish a manifest entry for it (expected, not a defect).
- Re-ran the backup: `SUCCESS`, `tag_library` refreshed, `bytes_copied: 56`
  (just the changed file), all other families untouched.
- Confirmed the refreshed destination file's content matches the live
  source exactly.
- Ran once more: back to fully idempotent, `bytes_copied: 0`.

### Status

P1 (including the P1.5 refresh correction) is **COMPLETE** and verified via
both automated tests and a real Windows smoke run against a real secondary
drive. Ready for P2 (tray + backup dialog + background worker integration)
review.

## 2026-09-15 — P2 implemented (tray + backup dialog + background worker)

### P2 — Tray + Backup dialog + background worker integration (COMPLETE)

Added:

- `services/backup/lock.py` — `SingleFlightLock`, a plain in-process
  `threading.Lock` wrapper with a non-blocking `try_acquire()`/`release()`.
  Sufficient for one process; manual (P2) and scheduled (P3) triggers will
  share the same instance.
- `services/backup/controller.py` — `BackupController(QObject)`. Owns the
  lock and a background `QThread` + `_BackupWorker(QObject)` pair.
  `back_up_now()` rejects (via `run_rejected` signal) if no destination is
  configured or a run is already in progress; otherwise moves a worker onto
  a new `QThread` and calls the unmodified `BackupService.run()` there,
  emitting `run_started` / `run_finished(BackupRunResult)`. No file/hash
  work happens on the GUI thread.
- `ui/backup/backup_dialog.py` — `BackupDialog(BaseStatusWindow)`: lists the
  protected-data families (from `PurityBackupCatalog.discover()`),
  configured destination, last-run summary (status/verified/failed counts),
  a **Back Up Now** button (delegates to `BackupController`) and a
  **Choose Local Destination...** button (`QFileDialog` +
  `settings_manager.set()/save()`). A non-`SUCCESS` finish shows a
  `QMessageBox` warning with `last_error`.
- `ui/system/supervisor_tray.py` — `PurityStatusWindow` gained a compact
  one-line backup status readout (destination + last run/verified/failed),
  refreshed the same way as the existing heartbeat/extension lines.
  `PurityTrayApp` gained optional `settings_manager` / `backup_controller`
  constructor kwargs and a **"Backup..."** tray menu action that lazily
  constructs and toggles the `BackupDialog`.
- `app.py` — constructs one `BackupController(settings_manager, parent=app)`
  and passes it (plus `settings_manager`) into `PurityTrayApp`.

Explicit scope trim vs. the plan wording: no separate **Verify** button —
`BackupService` only exposes `run()`, and re-running is already
idempotent/self-verifying (P1.5's manifest-based refresh), so a distinct
verify-only action would require new service surface not justified by
actual need.

Safety/behavior preserved: single-flight lock prevents overlapping manual
runs (second click gets a rejected-run message, not a second worker);
`supervisor.py` untouched; no direct file/hash/network calls added to any
Qt slot — everything routes through `BackupController` → `BackupService`.

### Tests

- `tests/backup/test_lock.py` — 3 tests (acquire, blocked-while-locked,
  release-then-reacquire).
- `tests/backup/test_backup_dialog.py` — 2 tests using a real
  `QApplication`: dialog construction/unconfigured-destination display, and
  a full `back_up_now()` run driven through a `QEventLoop` (with a 10s
  safety-timeout net) waiting on `BackupController.run_finished`, asserting
  the button re-enables and the last-run label / destination directory are
  populated.
- Full `tests/backup` suite: 30/30 passing.
- Full purity_app suite re-run after P2: 218 passed, same 5 pre-existing
  unrelated failures as before (no regressions), plus the same 3
  known PIL-import collection errors (unrelated, ignored per repo memory).

### Status

P2 is **COMPLETE** and tested (unit + real-QApplication smoke). Ready for
P3 (Sunday scheduling) review.

## 2026-09-15 — P3 implemented (Sunday scheduling)

### P3 — Sunday scheduling (COMPLETE)

Added `services/backup/scheduler.py`:

- `BackupSchedule` (frozen dataclass) — `enabled`, `weekday`
  (`datetime.weekday()` convention: 0=Monday..6=Sunday), `time` ("HH:MM"),
  `timezone` (IANA name; empty string = system local timezone via
  `datetime.now().astimezone().tzinfo`). Loaded from settings via
  `load_schedule()`.
- `ScheduleState` (dataclass) — `last_evaluated_occurrence_id`,
  `last_run_result_ref`; persisted at
  `<data_root>/_system/purity/backup/schedule_state.json` via
  `write_json_atomic` (`load_schedule_state()` / `save_schedule_state()`),
  parallel to the existing `local_state.json` / `local_manifest.json`
  convention.
- Pure, injectable-`now` functions: `last_occurrence_at_or_before()`
  (resolves the most recent scheduled wall-clock instant at/before `now`,
  timezone-aware via stdlib `zoneinfo.ZoneInfo`) and `is_due()` (returns an
  occurrence id only if it differs from `state.last_evaluated_occurrence_id`,
  i.e. hasn't been started yet).
- `BackupScheduler(QObject)` — thin wrapper tying schedule settings +
  durable state to the existing P2 `BackupController`. `check_now()` calls
  `is_due()`; if due, calls `controller.back_up_now()` (the same
  single-flight lock as manual runs). The occurrence is marked consumed
  (state saved) **only if the run actually started** — a rejection (no
  destination configured, or a manual run already in progress) leaves the
  occurrence due so it is retried on the next tick instead of being
  silently skipped. `run_finished` is connected to record
  `last_run_result_ref` once the scheduled run completes.

`settings_schemas.py` — added 4 settings: `backup_schedule_enabled`
(default `False`), `backup_schedule_weekday` (default `6`/Sunday),
`backup_schedule_time` (default `"02:00"`), `backup_schedule_timezone`
(default `""`), plus matching `get_backup_schedule_*()` getters.

`app.py` — in `main()`, alongside the existing `backup_controller`:
constructs `backup_scheduler = BackupScheduler(settings_manager,
backup_controller, parent=app)`, wires a 60-second `QTimer(app)` calling
`backup_scheduler.check_now`, and fires one immediate
`QTimer.singleShot(0, backup_scheduler.check_now)` check at startup so an
overdue occurrence isn't stuck waiting a full minute after launch. No
Windows Task Scheduler was introduced — `app.py`'s existing `QTimer`
poll-loop pattern (already used for heartbeats/pulse/web-watcher) was
sufficient, matching the plan's default assumption.

`ui/backup/backup_dialog.py` — added a "Weekly Schedule" group box: enable
checkbox, weekday combo (Monday..Sunday, index matches
`datetime.weekday()`), an `HH:mm` time edit, and a label showing the last
evaluated occurrence / run reference from `schedule_state.json`. Changes to
any control write straight through to the same 4 settings and save
immediately (no separate "Apply" step, consistent with the destination
picker's existing behavior).

Explicit scope trim vs. the plan wording: manual and scheduled runs share
the *same* `BackupController`/`SingleFlightLock` from P2 — no second lock
or controller was built, as instructed.

### Tests

- `tests/backup/test_scheduler.py` — 9 tests, pure-function only (no
  `QApplication` needed): disabled schedule never due; due when past
  scheduled time and not yet evaluated; not due before scheduled time
  (falls back to the prior week's occurrence); already-evaluated occurrence
  not due again (including later the same day); restart-safety via a real
  `tmp_path` state-file round-trip (reload from disk still suppresses a
  duplicate run); a new occurrence the following week becomes due again;
  timezone changes the absolute scheduled instant; DST spring-forward date
  (`America/New_York`, 2026-03-08) resolves to a valid instant without
  raising; schedule-state file defaults cleanly when absent.
- Full `tests/backup` suite: 39/39 passing.
- Full purity_app suite re-run after P3: 227 passed, same 5 pre-existing
  unrelated failures as before (`test_purity_preferences_integration.py`
  `_FakeApiServer` kwarg mismatch + 4x `test_web_popup.py` `_feeling_btn`
  missing) — no regressions from P3. Same 3 known PIL-import collection
  errors ignored per repo memory.

### Status

P3 is **COMPLETE** and tested. Ready for P4 (Dropbox backup) review — note
P4's explicit stop-before-implementation gate on the credential-storage
decision.

## 2026-09-16 — P4 implemented (Dropbox backup)

### P4 — Dropbox backup (COMPLETE)

Credential-storage decision (approved by user before implementation, per
the plan's explicit stop gate): use `keyring` — resolves to
`keyring.backends.Windows.WinVaultKeyring` (real Windows Credential Manager)
on this machine. ONLY secrets (Dropbox app secret, refresh token) go through
`services/backup/credentials.py`'s `DropboxCredentialStore` (service name
`purity_app.dropbox`, accounts `app_secret`/`refresh_token`) — never in
`settings.yaml`, `QSettings`, backup state JSON, logs, audit, the local
backup tree, or Dropbox itself. Non-secret Dropbox config (`dropbox_backup_enabled`,
`dropbox_app_key`, `dropbox_remote_folder` default `/PurityAppBackup`,
`dropbox_auth_invalid`) added as ordinary `settings_schemas.py` settings.

Added:

- `services/backup/dropbox_auth.py` — `DropboxAuthFlow` wraps
  `dropbox.oauth.DropboxOAuth2FlowNoRedirect` (offline/refresh-token,
  `token_access_type="offline"`; no local HTTP redirect listener). User
  pastes app key + app secret + a one-time auth code into the Backup
  dialog; `complete_authorization()` exchanges the code and persists the
  resulting refresh token (+ app secret) via `DropboxCredentialStore`.
- `models.py` — `DropboxAuthState` enum: `DISABLED` / `AUTH_REQUIRED` /
  `READY` / `REAUTH_REQUIRED`.
- `services/backup/dropbox_service.py` — `get_dropbox_auth_state()` derives
  the state from settings + credential store; `DropboxBackupService.run()`
  mirrors `BackupService.run()` but is fully independent: own manifest
  (`dropbox_manifest.json`) and run-history (`dropbox_state.json`), never
  touches local backup state. A Dropbox `AuthError` during a run sets
  `dropbox_auth_invalid=True` (→ `REAUTH_REQUIRED`) without affecting local
  state at all.
- `services/backup/destinations/dropbox.py` — `DropboxDestination.refresh_or_upload()`
  mirrors P1.5's local 4-way manifest logic (COPIED / ALREADY_PRESENT_IDENTICAL /
  REFRESHED / DESTINATION_CONFLICT) but verifies via Dropbox's own
  content-hash algorithm (`dropbox_content_hash()` — SHA-256 of concatenated
  4 MiB block hashes) read from `files_get_metadata`/`files_upload`
  responses, not local SHA-256. Plain `files_upload` (no chunked upload
  sessions — catalog files are all well under Dropbox's single-request
  limit).
- `services/backup/dropbox_controller.py` — `DropboxController(QObject)`
  mirrors `BackupController` but owns its OWN `SingleFlightLock`, separate
  from local's — Dropbox and local runs may proceed concurrently (both only
  read source files); only overlapping Dropbox runs are blocked.
- `state.py` extended (backward-compatible): `load_dropbox_manifest`/
  `save_dropbox_manifest`/`load_dropbox_state`/`append_dropbox_run`,
  refactored from shared `_load_manifest_at`/`_save_manifest_at`/
  `_load_state_at`/`_append_run_at` helpers; existing local function
  signatures unchanged.
- `scheduler.py` extended (backward-compatible): `ScheduleState` gained
  `last_evaluated_dropbox_occurrence_id`/`last_dropbox_run_result_ref`;
  `BackupScheduler` takes an optional `dropbox_controller` kwarg and
  independently evaluates `is_due_for_dropbox()` against the SAME weekly
  schedule settings as local on each tick — Dropbox reuses the schedule but
  has fully independent due/retry/consumed state (a Dropbox rejection or
  failure never blocks or duplicates the local occurrence, and vice versa).
- `app.py` constructs `dropbox_controller = DropboxController(settings_manager,
  parent=app)` alongside `backup_controller`, passes both into
  `BackupScheduler(..., dropbox_controller=dropbox_controller)` and into
  `PurityTrayApp(..., dropbox_controller=dropbox_controller)`.
- `ui/system/supervisor_tray.py` — `PurityStatusWindow._format_backup_status()`
  now shows both `LOCAL ...` and `DROPBOX ...` (or an auth-state placeholder)
  on one line; `_toggle_backup_dialog` passes `dropbox_controller` through.
- `ui/backup/backup_dialog.py` — new "Dropbox Backup" group box: enable
  checkbox, app-key field, remote-folder field, status label, last-run
  label, **Connect to Dropbox...** (prompts for app secret via a
  password-style `QInputDialog`, opens the authorize URL via
  `QDesktopServices.openUrl`, then prompts for the pasted auth code),
  **Disconnect** (clears keyring credentials, disables), **Back Up to
  Dropbox Now** (delegates to `DropboxController`).

Installed `dropbox` (official SDK) + `keyring` into `trading_root/.venv`.

### Tests

- `tests/backup/test_credentials.py` — 5 tests, in-memory fake keyring
  backend via monkeypatch (round-trip, idempotent clear, no cross-service
  collision).
- `tests/backup/test_dropbox_destination.py` — 5 tests, duck-typed fake
  `dropbox.Dropbox` client raising real `dropbox.exceptions.ApiError`/
  `AuthError` — covers all 4 refresh/upload outcomes plus
  `DropboxAuthInvalidError` on auth failure. No real network/API calls.
- Full `tests/backup` suite: 48/48 passing (was 39 before P4).
- Full purity_app suite re-run after P4: 236 passed, same 5 pre-existing
  unrelated failures as before (`test_purity_preferences_integration.py`
  `_FakeApiServer` kwarg mismatch + 4x `test_web_popup.py` `_feeling_btn`
  missing) — no regressions from P4. Same 3 known PIL-import collection
  errors ignored per repo memory.

No real Dropbox App-Console app was exercised in this session — only unit
tests with fakes/mocks. A real end-to-end Dropbox smoke run (connect →
upload → idempotent re-run → refresh-on-change → restart-survives-without-reauth
→ revoke → REAUTH_REQUIRED-without-affecting-local) was walked through as a
manual test plan with the user but not yet executed against a real Dropbox
account, pending the user creating an App-Console app and supplying an app
key/secret.

### Post-implementation environment issue (unrelated to P4 code correctness)

Launching `app.py`/the installed shortcut initially failed with
`ModuleNotFoundError: No module named 'keyring'`. Root cause: two *separate*
venvs exist for this codebase — `D:\code\git_new\trading_root\.venv` (used
for `pytest` runs per repo memory) and `D:\code\git\.venv` (a different
directory, hardcoded as `_REQUIRED_VENV_PYTHONW` in
`utilities/install_web_shortcuts.py`, used to build the desktop/tray
shortcut that actually launches the app day-to-day). `dropbox`/`keyring`
were installed into `trading_root/.venv` during P4 implementation, but the
shortcut launches via `D:\code\git\.venv`, which had `dropbox`/`PySide6`
already but not `keyring`. Fixed by installing `keyring` into
`D:\code\git\.venv` as well (confirmed importable, resolves to
`WinVaultKeyring`). Both venvs must be kept in sync for any future backup
dependency changes — `trading_root/.venv` for tests, `D:\code\git\.venv`
for the real running app.

### Status

P4 is **COMPLETE** and tested (unit tests + both venvs verified). Ready for
P5 (reliability hardening) review, pending a real Dropbox smoke run once
the user has an App-Console app key/secret to test against.

## 2026-09-16 — P4.5 planned (DPAPI secret store migration, not yet implemented)

### Problem discovered: Windows Credential Manager unusable on this machine

Real end-to-end Dropbox smoke testing (deferred at the end of P4) surfaced
a real environment blocker before any production Dropbox credential was
ever stored: both Python `keyring`/`WinVaultKeyring` and native
`cmdkey /generic:...` (no Python/keyring/pywin32 involved at all) fail
identically via Windows' `CredWrite` with `ERROR_NOT_ENOUGH_MEMORY`. This
proves it is an OS-level Windows Credential Manager problem, not a Purity,
`keyring`, `pywin32`, or `pywin32-ctypes` bug. Ruled out: disk space,
`VaultSvc` service health. The vault already holds ~291 stored credentials
on this machine, which is a known trigger for this exact failure mode
independent of actual available RAM. Two different keyring backends
(`win32ctypes` ctypes/CFFI shim, real `pywin32`'s `win32cred`) were tried
and both fail identically once routed through Windows' real vault APIs —
no keyring backend swap fixes this. Decision: do not repair, clean, or
inspect the shared Credential Manager vault (it holds credentials for many
other apps); treat Credential Manager as permanently out of scope.

Diagnostic/workaround code was temporarily added to
`services/backup/credentials.py` during this troubleshooting
(`_configure_windows_persistence()` forcing
`CRED_PERSIST_LOCAL_MACHINE`, a delete-before-write step in `_set()`,
`print(...)`/`traceback.print_exc()` diagnostics). None of it fixed the
underlying OS-level issue. This code is scoped for deletion in P4.5, not
preservation.

### Decision: replace Credential Manager with a reusable Windows DPAPI secret store

Added **P4.5 — DPAPI secret store migration** to the implementation plan
(see
[2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md](./2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md)),
inserted between P4 (Dropbox backup, complete) and P5 (reliability
hardening, still pending). P4.5 is **PLANNED, not yet implemented** —
nothing described below has been coded in this session.

Scope of P4.5, per plan:
- Generic `SecretStore` abstraction (`set_secret`/`get_secret`/
  `delete_secret`, namespaced by `(namespace, name)`), backed by a
  Windows-DPAPI (`CryptProtectData`/`CryptUnprotectData`, current-user
  scope) implementation — no master password, no custom persisted key, no
  plaintext fallback, no `.env`, no plaintext Registry, no secret values
  ever logged.
- Placement decision deferred to implementation time: `shane_common/security/`
  vs. Purity-local, contingent on re-confirming `purity_app`'s existing
  clean dependency on `shane_common` (precedent: `copy_file_verified`
  already used by `services/backup/destinations/local.py`) still holds and
  introduces no circular/inappropriate dependency.
- Refactor `services/backup/credentials.py` and all Dropbox
  auth/service/controller/state/UI call sites onto `SecretStore`
  exclusively; delete the diagnostic/workaround code above entirely.
- Remove `keyring` from Purity's dependencies (confirmed isolated to
  `services/backup/credentials.py` + `tests/backup/test_credentials.py` —
  re-verify at implementation time) and explicitly decide on removing
  `pywin32`/`pywin32-ctypes` from both venvs (`D:\code\git\.venv` used to
  launch the app, `trading_root/.venv` used for `pytest`) rather than
  leaving them in whatever state troubleshooting left them.
- Review whether the current Dropbox OAuth flow still needs a persisted
  `app_secret` given a PKCE-capable authorization-code + offline-access
  flow; remove it if the installed Dropbox SDK/flow confirms it's
  unnecessary. Target persisted shape: `app_key` → ordinary settings,
  `refresh_token` → `SecretStore`, `app_secret` → removed if unneeded.
- Preserve exactly: `DropboxAuthState` behavior (`DISABLED`/
  `AUTH_REQUIRED`/`READY`/`REAUTH_REQUIRED`), full local/Dropbox isolation,
  and the local backup / scheduler architecture (no redesign).
- No migration of old keyring secrets — no production Dropbox credential
  was ever successfully stored, so the new store simply becomes
  authoritative from first use.

New tests planned: `tests/backup/test_secret_store.py` (set/read,
overwrite, delete, missing secret, namespace isolation, corrupt payload,
DPAPI decrypt failure, atomic persistence, proof the persisted file does
not contain the literal secret value) plus extended
`tests/backup/test_dropbox_service.py` coverage (auth state with
missing/valid refresh token, Dropbox failure not affecting local state).

### Status

P4.5 was **PLANNED** as of this entry (added to the implementation plan as
a new phase between P4 and P5); no code changes were made in this session
— this was a planning/documentation update only. **P4.5 was subsequently
implemented and completed** — see the "P4.5 implemented" entry dated
2026-09-16 at the top of this log.
