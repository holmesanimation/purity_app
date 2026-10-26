# Purity App Backup — Chat Snippets v1.0

Companion to
[2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md](./2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md).

Each snippet below is self-contained and ready to paste into a **fresh
VSCode chat** to begin that specific phase. Paste only the snippet for the
phase you are starting.

---

## P1 snippet — Manual verified local backup

```text
Implement Phase P1 (Manual verified local backup) of the Purity App backup
work, exactly as scoped in:

  D:\code\git_new\purity_app\docs\03_ACTIVE_WORK\2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md

Also read (context/history, do not repeat):

  D:\code\git_new\purity_app\docs\03_ACTIVE_WORK\2026-09-15_Purity_App_Backup_Phase_P0_Repository_Audit_v1_0.md
  D:\code\git_new\purity_app\docs\03_ACTIVE_WORK\2026-09-15_Purity_App_Local_and_Dropbox_Backup_Revised_Scaled_Down_Phased_Plan_v2_0.md

Status: P0 is COMPLETE. P1 is NEXT. Do not repeat P0's audit work, but treat
current repository code as authoritative if it differs from either document.

Project root is explicitly D:\code\git_new\purity_app. Do not touch
trading_root or shane_common except to import/reuse existing generic
primitives (copy_file_verified, sha256_file, write_json_atomic).

Scope for this phase ONLY:
- PurityBackupCatalog resolving the fixed P1 family list (notes, Bible
  library, Bible memorizing list, prayer recipients, prayer prayed state,
  tag library, reminders override if present, user preferences).
- One configured secondary-drive destination (plain settings path, not
  StorageRegistry, unless you find a concrete reason otherwise).
- Verified COPY_ONLY backup using shane_common.runtime.transfer.copy_file_verified.
- Durable backup run/result state via shane_common.io.atomic.write_json_atomic.
- Safe handling of non-atomic BibleLibrary/TagLibrary writes (bounded
  retry-on-hash-mismatch, not a source-writer change).
- Deterministic destination layout, path validation, recursive-self-backup
  prevention.
- Tests using tmp_path against the real copy_file_verified primitive.
- A manual Windows smoke run.

Explicit non-goals: no Qt/tray integration, no scheduling, no Dropbox, no
restore/mutation of source data, no StorageRegistry unless justified.

Before writing code, re-verify against the current repository:
- resolve_purity_data_root() behavior and current data_root value
- exact current paths for tags.json, notes JSONL, bible_library.json,
  prayer_recipients.json, prayer_prayed.json, reminders.yaml
- current settings_schemas.py structure for adding backup_local_destination

Required tests: tests/backup/test_catalog.py, test_service.py, test_state.py.

Required completion report: list files created/modified, confirm all P1
acceptance criteria from the implementation plan, note any unresolved
architecture question discovered during implementation.

Stop after P1 is complete and tested. Do not begin P2 work in this chat.
```

---

## P2 snippet — Tray + Backup dialog + background worker integration

```text
Implement Phase P2 (Tray + Backup dialog + background worker integration)
of the Purity App backup work, as scoped in:

  D:\code\git_new\purity_app\docs\03_ACTIVE_WORK\2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md

Before doing anything else, read the current state of P1 completion
evidence (progress log if it exists, otherwise the P1 code itself under
purity_app/services/backup/) rather than assuming the original plan's file
list still matches what was actually built. Re-verify BackupService's
actual method signatures from the real P1 code before wiring it up.

Project root is explicitly D:\code\git_new\purity_app.

Scope for this phase ONLY:
- Add a "Backup..." QAction to the existing tray menu
  (purity_app/ui/system/supervisor_tray.py).
- Add a compact backup summary block to the existing Status window.
- Add a detailed BackupDialog (BaseStatusWindow subclass).
- Run all backup work off the Qt GUI thread via a background worker.
- Wire manual "Back Up Now" through the same BackupService built in P1.
- Add the minimum single-flight lock needed to prevent overlapping runs.

Known architecture/invariants carried forward: app.py's QApplication
process is the execution owner, not supervisor.py; supervisor.py must not
change; no direct file/hash/network calls in Qt code, everything delegates
through a BackupController to BackupService.

Files/modules most likely involved:
  purity_app/ui/backup/backup_dialog.py
  purity_app/services/backup/lock.py
  purity_app/ui/system/supervisor_tray.py
  purity_app/app.py

Required repository discovery before changing code: read the actual
current tray construction point in app.py and supervisor_tray.py's current
menu structure before editing — do not rely on line numbers from the P0
audit.

Explicit non-goals: no scheduling, no Dropbox, no restore functionality.

Required tests: tests/backup/test_lock.py, a real-QApplication smoke test
for BackupDialog.

Required completion report: files created/modified, confirmation of P2
acceptance criteria, any deviation from the assumed BackupService interface.

Stop after P2 is complete and tested. Do not begin P3 work in this chat.
```

---

## P3 snippet — Sunday scheduling

```text
Implement Phase P3 (Sunday scheduling) of the Purity App backup work, as
scoped in:

  D:\code\git_new\purity_app\docs\03_ACTIVE_WORK\2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md

Before doing anything else, read the current P1/P2 completion evidence
(progress log if present, otherwise the actual code under
purity_app/services/backup/ and purity_app/ui/backup/) to confirm the
BackupController, single-flight lock, and worker interfaces actually built,
rather than assuming the original plan's shapes are unchanged.

Project root is explicitly D:\code\git_new\purity_app.

Scope for this phase ONLY:
- Simple weekly schedule: enabled/day/time/timezone, settings-backed.
- Due-occurrence persistence so each due occurrence executes exactly once,
  durable across app restarts.
- Schedule check hosted by app.py's existing QTimer-driven loop.
- Manual and scheduled runs must use the same BackupService and the same
  single-flight lock from P2 — do not build a second lock.

Do not introduce Windows Task Scheduler unless you find concrete evidence
in the current repository that app.py cannot reliably host this.

Files/modules most likely involved:
  purity_app/services/backup/scheduler.py
  purity_app/app.py
  purity_app/services/settings_schemas.py

Explicit non-goals: no Dropbox, no reliability-hardening beyond what's
needed for correct once-only scheduled execution.

Required tests: tests/backup/test_scheduler.py covering due-occurrence
computation, restart-safety (no duplicate execution), disabled-schedule
no-op, and timezone/DST edge cases.

Required completion report: files created/modified, confirmation of P3
acceptance criteria, any deviation found in the actual P2 lock/controller
interfaces.

Stop after P3 is complete and tested. Do not begin P4 work in this chat.
```

---

## P4 snippet — Dropbox backup

```text
Implement Phase P4 (Dropbox backup) of the Purity App backup work, as
scoped in:

  D:\code\git_new\purity_app\docs\03_ACTIVE_WORK\2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md

Before doing anything else, read the current P1–P3 completion evidence
(progress log if present, otherwise the actual code under
purity_app/services/backup/) to confirm the current BackupDestination /
BackupService shape, and re-verify that no dropbox dependency or Dropbox
code exists yet in this repository — do not assume the P0 audit's findings
are still accurate without re-checking.

Project root is explicitly D:\code\git_new\purity_app.

Scope for this phase ONLY:
- Dropbox destination abstraction behind a shared BackupDestination
  interface alongside the existing LocalFilesystemDestination.
- OAuth/authentication approach.
- Secure credential storage (Windows Credential Manager via keyring, or
  DPAPI via ctypes) — decide and document explicitly.
- Cloud target namespace, retry/conflict behavior.
- Independent local/cloud verification state (Dropbox failure must never
  affect local backup state or normal Purity operation).
- Remote verification using Dropbox-supported content/revision semantics,
  not assumed SHA-256 equivalence.
- Harmless restore/download smoke.

STOP BEFORE IMPLEMENTATION if secure credential storage has not been
decided and approved. Do not store Dropbox tokens in plaintext settings
YAML or ordinary QSettings under any circumstance.

Files/modules most likely involved:
  purity_app/services/backup/destinations/dropbox.py
  purity_app/services/backup/credentials.py
  purity_app/services/backup/service.py
  purity_app/services/backup/state.py
  purity_app/ui/backup/backup_dialog.py

Explicit non-goals: no restore UI beyond harmless download smoke, no
reliability-hardening framework beyond what Dropbox itself requires.

Required tests: tests/backup/test_dropbox_destination.py (mocked Dropbox
API), tests/backup/test_credentials.py (token storage round-trip).

Required completion report: files created/modified, confirmation of P4
acceptance criteria, the credential-storage decision made and why.

Stop after P4 is complete and tested. Do not begin P5 work in this chat.
```

---

## P5 snippet — Reliability hardening

```text
Implement Phase P5 (Reliability hardening) of the Purity App backup work,
as scoped in:

  D:\code\git_new\purity_app\docs\03_ACTIVE_WORK\2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md

Before doing anything else, read the current P1–P4 completion evidence
(progress log if present, otherwise the actual backup code and its tests)
to identify concrete, real gaps or failure modes actually observed or
plausible given the real implementation — do not invent hypothetical
requirements not grounded in the actual code.

Project root is explicitly D:\code\git_new\purity_app.

Scope for this phase is bounded by what the current implementation
actually needs, drawn from:
  single-flight robustness, source-change handling, destination-conflict
  handling, retry policy, interrupted-run recovery, stale-backup detection,
  operator notification, independent local/cloud failure state.

Explicit non-goal: do not build a generalized backup framework beyond what
the actual P1–P4 implementation requires.

Required tests: targeted regression tests for whichever concrete failure
modes are addressed in this phase.

Required completion report: which specific gaps were found and fixed,
files created/modified, and confirmation that a backup failure still never
affects normal Purity app operation.

Stop after P5 is complete and tested. Do not begin P6 work in this chat.
```

---

## P6 snippet — Restore proof

```text
Implement Phase P6 (Restore proof) of the Purity App backup work, as
scoped in:

  D:\code\git_new\purity_app\docs\03_ACTIVE_WORK\2026-09-15_Purity_App_Local_and_Dropbox_Backup_Implementation_Plan_v1_0.md

Before doing anything else, read the current P1–P5 completion evidence
(progress log if present, otherwise the actual backup code and tests) to
confirm the real BackupRunResult/state schema and family list actually
implemented, rather than assuming the original plan's shapes.

Project root is explicitly D:\code\git_new\purity_app.

Scope for this phase ONLY:
- Restore a selected backup run into a temporary verification root (never
  in-place).
- Verify hashes and expected files for every restore-required family
  actually implemented (notes, Bible library, Bible memorizing list,
  prayer recipients, prayer prayed state, tag library, reminders override
  if present, user preferences).
- Open/read representative content from each family to confirm it is
  actually usable, not just byte-identical.
- Document the restore procedure.
- Record successful restore verification as durable evidence.

Explicit non-goal: do NOT add an in-place destructive Restore button or
any production restore workflow beyond the temp-root verification.

Files/modules most likely involved:
  purity_app/services/backup/restore.py
  purity_app/tests/backup/test_restore.py

Required tests: tests/backup/test_restore.py restoring a real backup run to
tmp_path and verifying hashes + representative content per family.

Required completion report: files created/modified, confirmation of P6
acceptance criteria, and the location of the recorded restore-verification
evidence.

Stop after P6 is complete. This is the final phase of the plan.
```
