# Machine-Wide Storage, Backup, and Scheduling Service
## Architecture Direction and Trading Platform Integration

**Date:** 2026-09-15  
**Status:** Architecture discussion capture / implementation handoff  
**Scope:** Design direction only. No production code or storage configuration is changed by this document.

---

# 1. Purpose

The trading platform already has a mature, bespoke storage architecture with:

- `StorageRegistry` / `LegacyStorageContext` for semantic storage resolution;
- canonical trading roots:
  - `C:/TP_DATA`
  - `E:/TP_ARCHIVE`
  - `G:/TP_BACKTESTS`
  - `C:/TP_DOCS`
- trading-owned archive lifecycle policy;
- verified copy / hash / manifest / delete safety semantics;
- a PySide6 administrative GUI for archive maintenance;
- a read-only System Console / browser storage page.

A separate Purity application now also has persistent storage such as notes, and there are additional machine-wide data sets (for example photos) that should be protected by:

1. a secondary local backup; and
2. a Dropbox cloud backup.

The objective is to preserve the accepted trading-specific storage architecture while introducing a new **machine-wide storage protection service** that can manage arbitrary folders and application data without making the trading platform responsible for the entire computer.

---

# 2. Core Architectural Decision

Do **not** generalize the trading platform's `StorageRegistry` into a machine-wide authority.

The trading platform should continue to own:

```text
WHERE trading resources live
WHEN trading data becomes eligible for archival
HOW trading-domain lifecycle rules are interpreted
```

The new machine service should instead own:

```text
WHICH machine data should be protected
WHEN backup/protection jobs should run
WHERE secondary local backups should be written
WHERE cloud backups should be written
WHETHER those backups were verified successfully
```

This creates a clean separation between:

```text
TRADING STORAGE
    operational/domain storage semantics

MACHINE STORAGE SERVICE
    backup, replication, scheduling, verification, and observability
```

---

# 3. High-Level Architecture

```text
                       MACHINE STORAGE SERVICE
                    persistent background process
                               │
              ┌────────────────┼────────────────┐
              │                │                │
         Catalog / DB      Scheduler       Backup Engine
              │                │                │
              │                │           copy / hash /
              │                │           verify / manifest
              │                │                │
       configured sources      │                │
              │                │                │
   ┌──────────┼──────────────┬─┴───────────────┐
   │          │              │                 │
Trading    Purity App      Photos          Other folders
storage      files
```

A source can then be protected to:

```text
Source
   │
   ├──> Local backup destination
   │
   └──> Dropbox
```

A preferred protection chain is:

```text
Source
    -> verified local backup
    -> verified Dropbox backup
```

Cloud is never canonical runtime storage.

---

# 4. Trading Platform Boundary Must Remain Intact

The machine service must **not** decide whether live trading data is safe to move from:

```text
C:/TP_DATA
    ->
E:/TP_ARCHIVE
```

That remains trading-domain policy.

Trading-specific semantics include:

- authoritative COMPLETE state;
- the >= 7 full day hot-retention rule;
- MarketData sealed/completion semantics;
- simulation exclusions;
- `G:/TP_BACKTESTS` never migrating to `E:/TP_ARCHIVE`;
- domain-specific safety around active writers;
- family-by-family archival eligibility.

Therefore the ownership boundary should be:

```text
Trading platform
    C:/TP_DATA -> E:/TP_ARCHIVE
    trading-specific archival lifecycle
    authoritative completion rules

Machine Storage Service
    E:/TP_ARCHIVE -> secondary local backup
    E:/TP_ARCHIVE -> Dropbox

    G:/TP_BACKTESTS -> secondary local backup
    G:/TP_BACKTESTS -> Dropbox

    C:/TP_DOCS -> secondary local backup
    C:/TP_DOCS -> Dropbox
```

Other applications can be protected independently:

```text
Purity storage -> local backup -> Dropbox
Photos         -> local backup -> Dropbox
Documents      -> local backup -> Dropbox
```

---

# 5. Dynamic Machine-Wide Source Catalog

The machine service should be intentionally more dynamic than the trading taxonomy.

The Qt administration GUI should allow the user to:

- add a protected folder;
- browse for the folder;
- give it a display name;
- classify it;
- choose a local backup destination;
- choose a Dropbox destination;
- select its schedule;
- enable/disable protection;
- manually run or verify protection.

A conceptual source record:

```text
ProtectionSource

source_id
display_name
owner
source_path

classification
    application_data
    documents
    photos
    trading_archive
    trading_backtests
    backup_only
    other

local_backup
    enabled
    destination_profile
    destination_subpath

cloud_backup
    enabled
    provider
    destination_subpath

schedule_group
verification_policy
enabled
```

Example:

```text
Photos

Source:
C:/Users/<user>/Pictures

Classification:
photos

Local backup:
H:/MACHINE_BACKUP/photos

Cloud:
Dropbox:/MachineBackup/photos

Protection mode:
COPY_ONLY
```

Example:

```text
Purity App

Source:
<configured Purity storage root>

Classification:
application_data

Local backup:
H:/MACHINE_BACKUP/apps/purity

Cloud:
Dropbox:/MachineBackup/apps/purity

Protection mode:
COPY_ONLY
```

---

# 6. Protection Modes

For arbitrary folders selected through the GUI, the safe default must be:

```text
COPY_ONLY
```

This means:

```text
source remains canonical
copy
verify
record
never delete source
```

A destructive/archive-style mode should be a distinct concept:

```text
ARCHIVE_MOVE
```

and should **not** be generally available to arbitrary GUI-selected folders initially.

Trading archival is the clearest example of a domain-owned `ARCHIVE_MOVE`-style operation, where the trading platform determines eligibility and safety.

This prevents an ordinary folder such as Photos from accidentally inheriting trading-style source deletion semantics.

---

# 7. Destination Profiles

Destination definitions should be reusable rather than repeated per source.

Example:

```text
DESTINATIONS

LocalBackup
    backend: filesystem
    root: H:/MACHINE_BACKUP

DropboxPrimary
    backend: dropbox
    root: /MachineBackup
```

Then a source can reference them:

```text
source = photos

local_destination = LocalBackup
local_subpath = photos

cloud_destination = DropboxPrimary
cloud_subpath = photos
```

These are machine-service destination profiles.

They should **not** replace or become authoritative over the trading platform's own `StorageProfile` objects.

---

# 8. Persistent Agent + Separate Tray GUI

The machine storage application should behave as one product to the user, but technically be split into:

```text
machine_storage_agent
    persistent
    scheduler
    source catalog
    backup engine
    verification
    operation history/state
    Dropbox connection
    localhost API

machine_storage_tray
    PySide6
    tray icon
    administration GUI
    talks to machine_storage_agent
```

Important behavior:

```text
Closing the Qt GUI does NOT stop backup scheduling.
```

For the initial Windows implementation, a user-level background process launched at login is likely simpler than immediately making it a Windows Service.

A real Windows Service can be considered later without redesigning the storage model.

---

# 9. Generic Machine-Wide Scheduler

The machine storage service should own the **generic scheduling mechanism**.

This scheduler should eventually support a custom schedule per source or job.

For example:

```text
Photos Backup
    Sunday 02:00

Purity Backup
    Sunday 02:30

Trading Archive Maintenance
    Sunday 03:00

Trading Local Backup
    after Trading Archive Maintenance

Trading Dropbox Backup
    after Trading Local Backup
```

Initially, all jobs can use the same Sunday cadence if desired.

The design should still allow future schedules such as:

```text
weekly
daily
interval
manual_only
```

Possible configuration:

```text
schedule_type: weekly
days:
    - Sunday
time: 03:00
timezone: America/Edmonton
```

---

# 10. Scheduler vs. Domain Policy

A critical boundary:

```text
Machine Scheduler
    decides WHEN to invoke a job

Provider / Domain
    decides WHAT operation is being invoked

Domain policy
    decides WHETHER it is actually safe/eligible
    and HOW it is performed
```

For trading:

```text
Machine Storage Scheduler
    "invoke Trading Archive Maintenance Sunday at 03:00"
                    │
                    ▼
Trading Storage Provider
                    │
                    ▼
Trading archive policy
    COMPLETE?
    >= 7 full days?
    family enabled?
    destination available?
    safe to archive?
                    │
            yes ────┴──── no
             │             │
             ▼             ▼
          execute       NO_ACTION
```

The scheduler must not understand trading lifecycle rules.

---

# 11. Dependency-Based Scheduling

Do not force every future job to depend only on clock time.

The scheduling model should eventually support:

```text
TIME
DEPENDENCY_SUCCESS
MANUAL
```

Example:

```text
Trading Archive
    Sunday 03:00
        │
        ▼ success
Trading Local Backup
        │
        ▼ success
Trading Dropbox Backup
```

This is better than simply scheduling the three jobs at arbitrary times and assuming the prior job has finished.

Dependency-trigger support can be designed now and implemented later.

---

# 12. Trading Integration Model

The trading application itself should **not depend on the machine service** in order to operate.

Instead, the machine service should call into a trading integration boundary.

Preferred relationship:

```text
Machine Storage Agent
        │
        ▼
TradingStorageProvider
        │
        ▼
existing trading archive-maintenance APIs
        │
        ▼
ArchiveMaintenanceRunner
```

The actual trading archive logic should remain independently callable through:

```text
CLI
PySide6 trading GUI
tests
machine scheduler
```

Avoid:

```text
Trading archive logic
    embedded inside
Machine Scheduler
```

Prefer:

```text
ArchiveMaintenanceRunner
        ↑
TradingStorageProvider
        ↑
Machine Scheduler
```

The machine service may therefore become the long-term scheduling host without becoming the trading-domain authority.

---

# 13. Provider Abstraction

Introduce a provider abstraction for operations requiring domain-specific integration.

Conceptually:

```text
MachineStorageProvider

list_sources()
get_source_status()
list_operations()
execute_operation()
```

Potential providers:

```text
FilesystemProvider
    arbitrary folders selected in GUI

TradingProvider
    trading-owned storage roots and operations

PurityProvider
    optional later if Purity ever needs domain-specific behavior
```

Purity does not require a provider initially if it can simply be represented as a protected filesystem source.

Trading is different because its archive lifecycle has domain-specific rules.

---

# 14. Trading Provider Responsibilities

The TradingProvider can expose machine-protection-compatible information such as:

```text
get_storage_roots()
get_archive_lifecycle_state()
get_protection_sources()
get_registered_operations()
```

For example, it may expose these protected sources:

```text
TP_ARCHIVE
TP_BACKTESTS
TP_DOCS
```

and an operation such as:

```text
archive_maintenance
```

But it must not duplicate the trading path taxonomy or reconstruct canonical trading paths independently.

The trading platform remains the authority for those paths.

---

# 15. Failure Independence

An important invariant:

```text
If machine_storage_agent stops:
    trading continues normally
    trading storage resolution continues normally
    live trading is unaffected
    existing trading archive mechanisms remain callable
    machine backup simply becomes stale/pending
```

Likewise:

```text
If Dropbox is unavailable:
    local trading remains unaffected
    local archive remains authoritative
    local backup remains authoritative where configured
    cloud backup retries later
```

No backup dependency should become part of live trading success.

---

# 16. Reusing the Existing Trading Safety Machinery

The existing trading implementation has already developed useful generic safety concepts:

- scheduler/due-run logic;
- single-flight locking;
- durable maintenance state;
- copy engine;
- SHA-256 verification;
- durable migration ledger;
- idempotent retry;
- destination-conflict detection;
- source-change detection;
- dry-run support.

These are good candidates to generalize/promote into the machine storage service.

However, the following remain trading-specific:

```text
Trading FamilyProvider
authoritative completion checks
7-day hot-retention rule
MarketData exclusions
sim-run exclusions
TP_DATA -> TP_ARCHIVE eligibility
trading family enablement/policy
```

Long-term conceptual split:

```text
machine_storage
    BackupEngine
    Scheduler
    OperationLedger
    Verification
    DestinationAdapter
    DropboxAdapter

trading_system
    TradingStorageProvider
    TradingArchivePolicy
    Trading archive candidates
```

---

# 17. Windows Task Scheduler

The current trading implementation uses Windows Task Scheduler as a coarse wake-up mechanism.

Once the persistent machine agent and its scheduler are proven reliable, that can evolve from:

```text
Windows Task Scheduler
        ↓
Trading archive CLI
```

to:

```text
Machine Storage Agent
        ↓
Machine Scheduler
        ↓
TradingProvider
        ↓
ArchiveMaintenanceRunner
```

Windows Task Scheduler can then be retired for archive maintenance if it is no longer needed.

This should happen only after the machine agent's startup/restart/recovery behavior is proven.

---

# 18. Qt GUI Responsibilities

The machine-wide PySide6 GUI should be the mutating administrative surface.

Potential controls:

```text
Add protected folder
Remove protected source
Browse source path
Set classification
Choose local destination
Choose Dropbox destination
Choose schedule
Enable/disable
Run now
Verify now
Retry failed backup
View operation history
View errors
Edit destinations
```

The tray icon can expose quick actions such as:

```text
Open Storage Manager
Run Due Jobs
Pause Scheduling
View Last Result
Exit GUI
```

Exiting the GUI should not terminate the agent.

---

# 19. Trading System Console / Electron Page

The existing trading storage Console should remain read-only.

It can continue displaying trading-specific information:

```text
TRADING STORAGE
C:/TP_DATA
E:/TP_ARCHIVE
G:/TP_BACKTESTS
C:/TP_DOCS

Trading archive lifecycle
Last run
Next run
Eligible candidates
Failures
```

It can later add a machine-protection section:

```text
MACHINE PROTECTION

Machine storage agent: RUNNING

TP_ARCHIVE
    Local backup: VERIFIED
    Dropbox: VERIFIED

TP_BACKTESTS
    Local backup: VERIFIED
    Dropbox: STALE

TP_DOCS
    Local backup: VERIFIED
    Dropbox: VERIFIED
```

The Console remains read-only.

Therefore the UI boundary is:

```text
Qt machine-storage GUI
    MUTATING ADMINISTRATION

Trading System Console / Electron page
    READ-ONLY OBSERVABILITY
```

---

# 20. Recommended Repository Placement

The machine-wide service should be a sibling project rather than live inside `trading_root`.

Recommended structure:

```text
D:/code/git_new/
    trading_root/
    purity_app/
    shane_common/
    machine_storage/
```

Example package structure:

```text
machine_storage/
    src/machine_storage/
        agent/
        api/
        backup/
        catalog/
        destinations/
        providers/
        scheduler/
        state/
        verification/
        gui/
```

This preserves ownership boundaries between independent applications.

---

# 21. Suggested Core Data Model

A conceptual machine job:

```text
StorageJob

job_id
display_name
provider_id
operation
source_id
enabled

trigger
    TIME
    DEPENDENCY_SUCCESS
    MANUAL

schedule
    frequency
    days
    time
    timezone

dependency_job_id

last_run_at
last_status
last_verified_at
next_run_at
last_error
```

Examples:

```text
provider_id = filesystem
operation   = backup
source_id   = family_photos
```

and:

```text
provider_id = trading
operation   = archive_maintenance
```

The scheduler does not need to understand the semantics of `archive_maintenance`.

---

# 22. Local and Cloud Backup State Must Be Independent

Protection state should not collapse local and cloud success.

Example:

```text
Photos

Source:
HEALTHY

Local backup:
VERIFIED
last_verified: ...

Dropbox:
FAILED
last_verified: ...
last_error: ...
```

Likewise for trading:

```text
TP_ARCHIVE

Trading archive state:
HEALTHY

Secondary local backup:
VERIFIED

Dropbox:
STALE
```

This preserves the already-established principle that local storage health, archival state, and cloud verification are separate concepts.

---

# 23. Recommended Implementation Sequence

## Phase 1 — Standalone machine storage foundation

Create:

- persistent agent;
- PySide6 tray application;
- source catalog;
- destination profiles;
- generic scheduler;
- persistent state;
- localhost API;
- Sunday scheduling.

Do not integrate Dropbox yet.

## Phase 2 — Generic verified local backup

Generalize/promote reusable safety machinery:

```text
copy
hash
verify
operation ledger
retry
idempotency
conflict detection
source-change detection
dry-run
```

Support `COPY_ONLY`.

Test first with:

- an isolated mock folder;
- then a low-risk personal folder;
- then photos/Purity data.

## Phase 3 — TradingProvider

Register:

```text
E:/TP_ARCHIVE
G:/TP_BACKTESTS
C:/TP_DOCS
```

as protected machine sources.

Expose trading archive-maintenance as a provider operation.

Do not change the existing `C:/TP_DATA -> E:/TP_ARCHIVE` policy.

## Phase 4 — Scheduler integration

Allow the machine scheduler to invoke:

```text
TradingProvider.archive_maintenance
```

Keep the underlying `ArchiveMaintenanceRunner` independently callable.

Initially use Sunday scheduling.

Later support dependency chains.

## Phase 5 — System Console observability

Add read-only projection of:

- machine agent state;
- registered protected trading roots;
- next backup;
- local backup verification;
- cloud verification;
- recent failure.

Do not add controls to the browser.

## Phase 6 — Dropbox destination adapter

Add Dropbox as a machine-wide destination.

Cloud backup remains:

```text
asynchronous
verified
non-canonical
non-blocking
```

Maintain independent state for:

```text
E:/TP_ARCHIVE
G:/TP_BACKTESTS
C:/TP_DOCS
Purity
Photos
other folders
```

## Phase 7 — Retire temporary scheduling infrastructure

After the machine agent is proven reliable:

- retire the temporary Windows Task Scheduler archive wake-up if desired;
- retain trading CLI/manual execution paths;
- retain machine-service-independent trading behavior.

---

# 24. Final Ownership Model

```text
Trading StorageRegistry
    WHERE trading data lives

Trading lifecycle policy
    WHEN trading data may become archive data

Trading archive runner
    HOW trading archival is performed safely

Machine Storage Service
    WHICH machine data requires protection
    WHERE secondary local backups live
    WHERE cloud backups live
    WHEN backup/protection jobs are invoked
    WHETHER backups were verified

Machine Scheduler
    WHEN

Provider
    WHAT operation

Domain
    WHETHER it is safe
    HOW it is performed

Qt machine-storage GUI
    mutating administration

Trading System Console / Electron page
    read-only observability
```

---

# 25. Key Invariants

```text
1. Trading does not depend on the machine storage service to run.
2. The machine service does not recreate trading storage taxonomy.
3. The machine scheduler does not own trading lifecycle policy.
4. Arbitrary GUI-added folders default to COPY_ONLY.
5. No generic folder backup deletes source data.
6. Cloud is never canonical runtime storage.
7. Local backup and cloud verification state are independent.
8. Closing the tray GUI does not stop the persistent agent.
9. The trading Console remains read-only.
10. The machine service may invoke trading archive operations, but trading decides eligibility.
11. G:/TP_BACKTESTS never becomes an E:/TP_ARCHIVE archival source.
12. TP_DATA -> TP_ARCHIVE remains a trading-domain lifecycle relationship.
13. Dependency-triggered jobs should be supported conceptually even if initial implementation uses only Sunday schedules.
14. Existing verified-copy/hash/manifest safety concepts should be reused rather than reinvented.
```

---

# 26. Architectural Summary

The recommended evolution is not to replace the trading storage system.

Instead:

```text
KEEP
    trading-specific semantic storage
    trading-specific archive eligibility
    trading-specific lifecycle policy
    existing read-only Console

PROMOTE / GENERALIZE
    scheduling
    verified copying
    hashing
    manifests / operation ledgers
    retry/idempotency
    destination management
    backup observability

ADD
    persistent machine agent
    machine-wide source catalog
    per-folder/per-job schedules
    generic filesystem provider
    TradingProvider
    PySide6 tray/admin GUI
    local secondary backup destinations
    Dropbox destination adapter
```

This allows the existing trading platform, Purity application, personal photos, and future machine data to use one coherent backup and scheduling service while retaining the domain boundaries and safety rules already established for trading.
