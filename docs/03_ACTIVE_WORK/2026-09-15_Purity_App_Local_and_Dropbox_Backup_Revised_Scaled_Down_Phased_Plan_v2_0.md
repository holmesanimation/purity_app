# Purity App Local + Dropbox Backup
## Revised Scaled-Down Phased Implementation Plan

**Date:** 2026-09-15  
**Status:** Proposed implementation plan / repository-audit handoff  
**Scope:** Purity App only. This is intentionally **not** the future machine-wide centralized storage service.

## 1. Purpose

The Purity App already has a persistent background/supervisor process, a PySide6 tray application, an existing `Purity — Status` dialog, and shared watchdog/liveness infrastructure from `shane_common`.

The immediate goal is to add reliable backup of all restore-required Purity data to:

1. a configured secondary local drive; and
2. Dropbox cloud storage.

The implementation should reuse existing infrastructure where appropriate, but remain Purity-focused. The source data remains authoritative. Purity backup is **COPY_ONLY**: no source deletion or archive-move semantics are introduced.

## 2. Data that must be protected

The repository audit must identify the actual authoritative roots/files for all durable Purity data, including at minimum:

```text
notes
journals
check-ins
prayer recipients / prayer database
Bible library
tag library
```

Also identify any additional persistence required for a complete restore.

Classify each discovered family as:

```text
DURABLE / RESTORE-REQUIRED
OPTIONAL / REBUILDABLE
TRANSIENT / EXCLUDE
SYSTEM / WATCHDOG / EXCLUDE unless specifically justified
```

Do not assume everything under one data root belongs in backup.

## 3. Existing runtime context

Current Purity code already uses shared `shane_common.watchdog` infrastructure:

```text
PuritySupervisorClient
    -> HeartbeatReader
    -> AppendOnlyAuditLog

PurityTrayApp
    -> BaseTrayApp
    -> system tray
    -> Show Purity
    -> Show Status
    -> Reload
    -> Show Panic Button
    -> Quit

PurityStatusWindow
    -> BaseStatusWindow
    -> Purity heartbeat status
    -> extension heartbeat status
```

The backup feature should therefore **not** create another tray app or background daemon unless the audit proves one is necessary.

## 4. First architectural question: who owns backup execution?

Before coding, audit the actual Purity supervisor/background runtime.

The likely preferred split is:

```text
SUPERVISOR / LONG-LIVED BACKGROUND OWNER
    schedule evaluation
    backup execution orchestration
    locking/retry
    durable backup state

TRAY APP
    operator controls
    status display
    manual Back Up Now request
    notifications
```

The supervisor should call a dedicated `BackupService`; copy/hash/Dropbox logic should not be embedded directly in supervisor code.

Do not freeze this until the audit confirms:

```text
1. supervisor lifetime and restart model
2. whether it already owns scheduled/background work
3. event-loop/timer capability
4. IPC/request path from tray to supervisor
5. error isolation requirements
6. whether backup work could interfere with watchdog duties
```

If the supervisor is not an appropriate owner, the audit should recommend the smallest alternative without creating a machine-wide service.

## 5. Tray and GUI recommendation

Keep the existing Status dialog concise and add a separate detailed Backup dialog.

Recommended tray menu:

```text
Show Purity
Show Status
Backup...
Reload
Show Panic Button
----------------
Quit
```

Recommended Status summary:

```text
purity_app: HEALTHY
extension heartbeat: HEALTHY

backup:
    LOCAL: VERIFIED — last success <time>
    DROPBOX: VERIFIED — last success <time>
    next run: Sunday <time>
```

Recommended `Backup...` dialog:

```text
BACKUP

Protected Data
    Notes                 INCLUDED
    Journals              INCLUDED
    Check-ins             INCLUDED
    Prayer Recipients     INCLUDED
    Bible Library         INCLUDED

Local Backup
    Destination: <path>
    Status: VERIFIED / FAILED / NEVER_RUN / RUNNING
    Last successful backup: ...

Dropbox
    Destination: /Purity/...
    Status: VERIFIED / FAILED / NEVER_RUN / RUNNING
    Last successful backup: ...

Schedule
    Enabled: [x]
    Day: Sunday
    Time: ...
    Timezone: ...

[ Back Up Now ]
[ Verify ]
[ Choose Local Destination ]
[ Configure Dropbox ]
```

The Qt UI must not perform copying, hashing, schedule evaluation, or Dropbox operations directly.

## 6. Core safety model

Purity backup is always:

```text
COPY_ONLY
```

Never:

```text
copy -> verify -> delete source
```

Local and Dropbox states are independent:

```text
NEVER_RUN
RUNNING
VERIFIED
FAILED
STALE
```

Dropbox failure must not invalidate a successful local backup. Backup failure must never stop Purity from running.

# 7. Phase P0 — Repository + Shared-Infrastructure Audit

This phase is mandatory before implementation.

## P0-A — Inventory Purity persistence

For notes, journals, check-ins, prayer recipients, Bible library, and any additional restore-required family, record:

```text
family
authoritative source path
format
writer(s)
reader(s)
mutable while app runs?
atomic-write behavior?
safe to copy while running?
restore requirements
include/exclude decision
```

## P0-B — Inspect supervisor ownership

Audit:

```text
supervisor entry point
lifetime / restart model
timers / event loop
IPC / command paths
shutdown behavior
single-instance behavior
persistent state location
error isolation
```

Determine whether the supervisor should own schedule execution.

## P0-C — Inspect tray/status infrastructure

Audit `PurityTrayApp`, `PurityStatusWindow`, supervisor client, and reusable `shane_common.watchdog` components.

Determine whether generic status-row, settings, worker, notification, command, or dialog patterns already exist.

## P0-D — Audit `shane_common` for reusable storage/backup primitives

Search before creating Purity-specific implementations:

```text
StorageRegistry / StorageProfile / StorageLocation
filesystem availability probing
hashing helpers
atomic JSON/state persistence
single-flight/file locking
schedule/due-occurrence evaluation
copy/verify utilities
manifest/ledger primitives
retry helpers
Dropbox/cloud abstractions
background-worker helpers
```

Reuse only genuinely domain-neutral mechanisms.

## P0-E — Consult trading storage work as non-governing prior art

Use the current trading storage progress log/designs only to identify proven generic patterns such as:

```text
copy -> verify -> durable state
SHA-256 verification
single-flight locking
idempotent retry
destination conflict handling
source-change detection
schedule due-state persistence
GUI/controller separation
cloud as non-canonical asynchronous backup
```

Do **not** inherit:

```text
trading resource taxonomy
TP_DATA / TP_ARCHIVE semantics
7-day retention
archive eligibility
MarketData policy
source-deletion gates
System Console architecture
```

### P0 deliverable

Produce a concise audit artifact containing:

```text
Purity backup source inventory
recommended execution owner
available shane_common primitives
missing generic primitives
proposed module placement
UI integration recommendation
local destination configuration
Dropbox integration approach
test strategy
```

Stop for review if material architecture ambiguity remains.

# 8. Phase P1 — Manual Verified Local Backup

Implement local backup first, before scheduling or Dropbox execution.

Prefer an explicit audited catalog:

```text
PurityBackupCatalog
    notes
    journals
    checkins
    prayer_recipients
    bible_library
```

Resolve source paths from existing Purity storage authority/configuration. Do not create a second authority for Purity source locations.

For every protected file:

```text
discover
    -> capture source identity
    -> copy safely
    -> verify size
    -> SHA-256 source
    -> SHA-256 destination
    -> compare
    -> record VERIFIED
```

Persist at least:

```text
run_id
started_at
completed_at
status
source families
destination
file_count
verified_count
failed_count
bytes_copied
last_error
```

Acceptance:

```text
[ ] All restore-required families included.
[ ] Transient exclusions documented.
[ ] Manual secondary-drive backup succeeds.
[ ] Every copied file verified.
[ ] Source untouched.
[ ] Re-run safe/idempotent.
[ ] Missing destination fails visibly.
[ ] Unit/integration tests use temporary roots.
[ ] Harmless Windows smoke passes.
```

# 9. Phase P2 — Supervisor Integration + Tray Control

Move execution into the accepted long-lived owner identified in P0.

Preferred flow if supervisor is suitable:

```text
Purity Tray
    -> request Back Up Now
Purity Supervisor
    -> BackupService
```

Do not run heavy copy/hash work on the Qt UI thread.

Add:

```text
Backup...
```

to tray menu, compact backup status to the Status dialog, and a dedicated backup dialog.

Acceptance:

```text
[ ] Tray requests backup through background owner.
[ ] UI remains responsive.
[ ] Status shows local backup health.
[ ] Backup dialog shows detailed run state.
[ ] Same tested BackupService is used.
[ ] Watchdog/liveness behavior unaffected.
```

# 10. Phase P3 — Scheduled Local Backup

Add simple Sunday scheduling:

```text
enabled
weekday
time
timezone
```

Persist occurrence identity so a due occurrence executes once.

If the supervisor is persistently running:

```text
Supervisor
    -> periodic schedule tick
    -> due?
    -> BackupService
```

Avoid Windows Task Scheduler unless the supervisor is not guaranteed to be available.

Acceptance:

```text
[ ] Schedule configurable.
[ ] Due occurrence runs once.
[ ] Restart does not duplicate completed occurrence.
[ ] Disabled schedule does not run.
[ ] Manual backup remains available.
[ ] Manual and scheduled paths use same service.
```

# 11. Phase P4 — Dropbox Backup

Add Dropbox inside the same backup-domain boundary.

Conceptually:

```text
BackupDestination
    LocalFilesystemDestination
    DropboxDestination
```

Do not force Dropbox to behave like a local filesystem.

Initial conceptual flow:

```text
Purity source
    +-> Local secondary backup
    +-> Dropbox backup
```

Local and cloud may share one schedule but must retain independent verification state.

Audit Dropbox specifics before implementation:

```text
authentication
secure credential storage
remote namespace
overwrite/version behavior
conflict behavior
large-file handling
rate limits/retry
remote verification
restore/download procedure
```

Credentials must remain outside source-controlled config.

Record at least:

```text
uploaded
verified
failed
unknown
```

Use Dropbox content/revision/hash evidence where available rather than assuming filesystem SHA-256 semantics map directly to Dropbox.

Acceptance:

```text
[ ] Dropbox and local state persisted independently.
[ ] Dropbox outage does not affect Purity operation.
[ ] Credentials are secure/outside source control.
[ ] Retry is idempotent.
[ ] Conflicts fail visibly.
[ ] Harmless restore/download smoke documented.
```

# 12. Phase P5 — Reliability Hardening

Add:

```text
single-flight execution
source-change detection
destination conflict handling
retry policy
interrupted-run recovery
stale-backup detection
operator notification
```

A backup failure is not an application failure.

# 13. Phase P6 — Restore Proof

A backup system is incomplete until restore is proven.

Restore to a temporary verification root, not in-place:

```text
select backup
    -> restore to temp root
    -> verify hashes/expected resources
    -> open/read representative data
    -> record restore verification
```

Cover at minimum:

```text
notes
journals
check-ins
prayer recipients
Bible library
```

Do not initially add a destructive in-place Restore button.

# 14. Recommended Module Shape

Exact placement should follow P0 findings.

Conceptually:

```text
purity_app/
    backup/
        catalog.py
        models.py
        service.py
        state.py
        scheduler.py
        controller.py
        destinations/
            local.py
            dropbox.py
        gui/
            backup_dialog.py
```

Move code into `shane_common` only when it is genuinely domain-neutral and not already available there.

# 15. How to use the trading storage documents

Yes: cite them **selectively in the audit/design as non-governing reference material**.

Recommended rule:

```text
Trading storage docs
    prior-art/reference for proven generic mechanisms

Purity checkout + shane_common
    current authority for Purity implementation
```

The audit should explicitly state:

> Trading storage documentation is consulted only for previously proven generic mechanism patterns. Purity-specific architecture is derived from the Purity checkout and current `shane_common` contracts. Trading-domain storage taxonomy and lifecycle policy are not inherited.

Prefer the current trading storage **progress log** when you need evidence of mechanisms actually implemented and proven.

Use the older implementation plan only selectively for broad principles such as generic-mechanism vs domain-policy ownership.

Do not inject large trading documents into every Purity coding prompt. Have P0 extract the specific generic contracts/patterns that are relevant.

# 16. Shared infrastructure ownership rule

```text
shane_common
    generic reusable mechanism

purity_app
    Purity storage catalog
    Purity backup policy/config
    Purity GUI
    Purity supervisor integration

trading_system
    trading-specific lifecycle/storage policy
```

Current Purity watchdog/tray code already follows this pattern by importing generic components from `shane_common`.

# 17. Explicit Non-Goals

Still out of scope:

```text
machine-wide arbitrary-folder catalog
new machine_storage service
trading backup integration
trading System Console integration
cross-application scheduler
source deletion / archive move
photo backup
whole-machine backup
remote backup administration
Windows Service migration
```

# 18. Recommended Sequence

```text
P0  Repository + shane_common + supervisor audit
        |
P1  Manual verified local backup
        |
P2  Supervisor integration + tray Backup dialog
        |
P3  Sunday local schedule
        |
P4  Dropbox destination + independent verification
        |
P5  Reliability hardening
        |
P6  Restore proof
```

# 19. Target End State

```text
Purity Supervisor
    +-- backup schedule
    +-- BackupService
    |     +-- audited PurityBackupCatalog
    |     +-- Local secondary drive
    |     +-- Dropbox
    +-- durable independent destination state

Purity Tray
    +-- Status summary
    +-- Backup... dialog
    +-- Back Up Now
    +-- notifications
```

Protected data includes at minimum:

```text
notes
journals
check-ins
prayer recipients
Bible library
```

plus additional restore-required durable resources found by P0.

# 20. Final Position

The expected architecture, subject to P0 confirmation, is:

```text
Supervisor   = background execution/scheduling host
Tray         = control + visibility
BackupService = backup logic
shane_common = generic reusable primitives
Purity       = owner of its storage catalog and backup policy
```

Use the trading storage work to avoid reinventing proven generic mechanisms, but keep it as reference material rather than Purity's authority.

This gives Purity verified secondary-drive + Dropbox backups now while preserving a clean future path toward the machine-wide storage service if multiple applications later need it.
