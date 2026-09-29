# Plan: Move Notes to SQLite, and Add Snapshot Backups

Status: IMPLEMENTED 2026-09-29 (phases 1-7, including the optional JSONL export). Written
2026-09-29. See "Implementation notes" at the end for how the open questions were resolved and
where the code deviates from this plan.

## 1. Goal and scope

Replace the per-owner JSONL notes files (and the separate owner/subject JSON registry) with a
single SQLite database that is the source of truth for notes, owners, subjects and correlations.
Change the backup system so it backs up a **consistent snapshot** of the database instead of
copying the live file, keeps **dated snapshots** instead of overwriting one file, and verifies
each snapshot before it can replace or prune anything.

Out of scope:
- **Migrating existing JSONL notes.** They are placeholder data. Move `purity_app/notes/` aside
  (do not delete until the new system is verified) and start with an empty database.
- New features (tag tables, full-text search, revision-history UI). The schema leaves room for
  them but this plan does not build them.
- Multi-machine sync. The live database must never be placed in a synced folder.

## 2. Decisions

| # | Decision | Reason |
|---|----------|--------|
| D1 | SQLite via the stdlib `sqlite3` module. No ORM. | No new dependency; the schema is small. |
| D2 | Keep the **append-only revision model**. Edit and delete are new rows in `revisions`; nothing is updated in place except a small "head pointer" on `notes`. | Preserves the history behaviour already built and tested. |
| D3 | Drop the v1/v2 note-shape split. One `revisions` row shape, with the table-row fields (`table_id`, `row_id`, ...) nullable. | The split existed only because of file history. |
| D4 | Every note has a real `note_id` from creation. Remove the derived `legacy_` ids. | No legacy data to support. |
| D5 | `UNSET` subject is stored as `subject_id IS NULL`. The string `"UNSET"` is a display/API value only. | Lets the foreign key stay enforceable. |
| D6 | WAL journal mode, `synchronous=FULL`, `foreign_keys=ON`. | Crash-safe; write volume is tiny so `FULL` costs nothing noticeable. |
| D7 | Flexible per-note data (`tags`, `tagged_verses`, `calories`, widget info) stays in a JSON `context` column. | Avoids modelling everything up front. |
| D8 | Backups use SQLite's online backup API into a staging file, verify it, then upload the staging file. **The live `.db`, `-wal` and `-shm` files are never copied.** | Copying a live SQLite file can produce a torn or incomplete backup. |
| D9 | Snapshots are dated files (`notes-YYYYMMDDTHHMMSSZ.db`) with a retention policy, never overwritten. | One overwritten copy means one bad write destroys the only good backup. |

## 3. Database design

File: `notes.db` (location: see open question Q1).

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);  -- schema_version, write_seq (bumped in every write transaction; used to skip unchanged backups)

CREATE TABLE owners (
  key    TEXT PRIMARY KEY,               -- stable slug, e.g. 'sleep_log'
  label  TEXT NOT NULL,                  -- display name, may contain spaces
  builtin INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE subjects (
  id        TEXT PRIMARY KEY,            -- 'subj_1a2b3c4d'
  label     TEXT NOT NULL,
  owner_key TEXT REFERENCES owners(key), -- NULL = available to all owners
  UNIQUE (owner_key, label COLLATE NOCASE)
);
-- NOTE: a per-owner and an all-owner subject with the same label must also be rejected;
-- SQLite's UNIQUE treats NULLs as distinct, so this rule stays in application code + a test.

CREATE TABLE notes (
  note_id    TEXT PRIMARY KEY,           -- make_note_id() format, unchanged
  owner_key  TEXT NOT NULL REFERENCES owners(key),
  created_ts REAL NOT NULL,
  head_rev   INTEGER NOT NULL,           -- newest revision_num
  deleted    INTEGER NOT NULL DEFAULT 0  -- 1 when head revision is a delete
);

CREATE TABLE revisions (
  note_id      TEXT NOT NULL REFERENCES notes(note_id),
  revision_num INTEGER NOT NULL,
  op           TEXT NOT NULL CHECK (op IN ('create','edit','delete')),
  ts           REAL NOT NULL,
  wall_ts      REAL NOT NULL,
  note_type    TEXT NOT NULL,
  title        TEXT,
  subject_id   TEXT REFERENCES subjects(id),   -- NULL = UNSET
  text         TEXT NOT NULL,
  instrument   TEXT,
  strategy_id  TEXT,
  context      TEXT NOT NULL DEFAULT '{}',     -- JSON
  -- optional table-row link (formerly "v2" notes)
  table_id TEXT, table_label TEXT, row_id TEXT, row_ts REAL, row_snapshot TEXT,
  owner_module TEXT, owner_class TEXT,
  PRIMARY KEY (note_id, revision_num)          -- also gives edit-conflict detection
);

CREATE TABLE correlations (
  correlation_id TEXT PRIMARY KEY, time_window TEXT, relation_type TEXT,
  hypothesis TEXT, tags TEXT, created_ts REAL NOT NULL
);
CREATE TABLE correlation_notes (
  correlation_id TEXT NOT NULL REFERENCES correlations(correlation_id),
  note_id        TEXT NOT NULL REFERENCES notes(note_id),
  row_id         TEXT,
  PRIMARY KEY (correlation_id, note_id)
);

CREATE INDEX idx_notes_owner_created ON notes(owner_key, created_ts DESC);
CREATE INDEX idx_revisions_subject   ON revisions(subject_id);
CREATE INDEX idx_revisions_row       ON revisions(row_id);
```

Behaviour notes:
- **Write path (one transaction):** insert the revision, insert/update the `notes` head
  (`head_rev`, `deleted`), bump `meta.write_seq`. All or nothing.
- **Edit conflicts:** two edits of the same revision collide on the primary key. The second fails
  with a clear "note was changed elsewhere" message rather than silently interleaving.
- **Current notes for an owner:** join `notes` to `revisions` on `(note_id, head_rev)` where
  `deleted = 0`, filter by `subject_id`, order by the head revision `ts DESC`.
- **Migrations:** `meta.schema_version` plus an ordered list of migration functions run at open.
  Version 1 is the schema above.
- **Integrity of the "same label" rule** for subjects and the owner-key rules stay in Python
  (they are already implemented in `registry.py`).

## 4. Code changes

New (in `shane_common`, generic, no Qt):
- `notes/db.py` - open/connect (pragmas, migrations, per-thread connections), `write_seq` helper.
- `notes/store.py` - `NotesStore`: `add_note`, `add_revision` (edit/delete), `notes_for_owner`,
  `note_history`, `add_owner`, `add_subject`, `list_owners`, `list_subjects`, correlations.
  Replaces the JSONL parsing in `notes_repository.py` and the file appends in `notes_writer.py`.

Kept with minimal change (this is why the UI work is small):
- `NoteRow` stays as the read model; drop `raw`, `schema_version`, `is_v2`, the `legacy_` id logic.
- `NotesRepository` keeps its method names (`rows_for_owner`, `latest_notes_for_owner`,
  `list_owners`, `latest_notes_for_row`, ...) but is backed by `NotesStore`. Callers such as the
  dock, calories total and verse history keep working.
- `NotesWriter` keeps `build_note`, `commit`, `for_owner` as a thin facade over `NotesStore`;
  `commit_v2` / `build_table_note` collapse into one path.
- `revisions.commit_revision` calls `NotesStore.add_revision`.
- `registry.py` becomes a facade over the `owners` / `subjects` tables; validation and the
  duplicate rules stay. `notes_registry.json` and its backup family go away.
- `services/notes_setup.py` creates the store from the configured DB path and
  registers the built-in owners on first open.

Removed: JSONL read/write code, `discover_jsonl_files`, `CORRELATIONS_FILENAME` handling, the
registry JSON file, the `notes` and `notes_registry` backup families.

UI (`note_dialog.py`, browser, dock, calories dialog): expected to need only import/constructor
adjustments. The browser's orphan-subject workaround can be deleted (foreign keys prevent it) and
its manual "latest revision" collapsing replaced by the store query.

## 5. Backup: snapshots

### 5.1 How the current backup works (for context)
`BackupService` and `DropboxBackupService` each call `PurityBackupCatalog.discover()` and run
every source file through a four-case refresh (`refresh_or_copy` / `refresh_or_upload`): copy if
absent, skip if identical, overwrite if the destination still matches the last recorded hash,
otherwise report `destination_conflict`. The destination path is fixed
(`<family>/<filename>`), so today a changed file is **overwritten**. `restore_backup` then copies
every family into a verification root and runs a per-family content check.

### 5.2 New behaviour
1. **Snapshot step** (new `services/backup/snapshot.py`), run at the start of each backup run:
   - Open the live DB read-only-ish and call `sqlite3.Connection.backup()` into a temp file in a
     staging dir (`<data_root>/_system/purity/backup/staging/`). This yields a consistent
     point-in-time copy even while the app is writing.
   - Verify the temp file: `PRAGMA integrity_check` returns `ok`, `PRAGMA foreign_key_check` is
     empty, `meta.schema_version` is readable, and row counts match the source at snapshot time.
     On any failure: delete the temp file, fail the run, **do not upload or prune anything**.
   - Skip if unchanged: compare `meta.write_seq` to the value recorded for the last good
     snapshot in backup state. If equal, reuse the previous snapshot and upload nothing.
   - Otherwise rename to `notes-YYYYMMDDTHHMMSSZ.db` and record `write_seq`, size and hash in
     backup state. Keep only the newest staging file locally.
2. **Catalog:** replace the `notes` and `notes_registry` families with one `notes_db` family whose
   path is the current staging snapshot (required=True). Because the filename is dated, every new
   snapshot is a brand-new file at the destination (case 1, `COPIED`) and can never trip
   `destination_conflict` or overwrite an earlier snapshot.
3. **Retention** (new `prune_family()` on both destinations), run only after the new snapshot
   has been uploaded **and** verified:
   - Keep the newest 14 snapshots plus the newest snapshot of each of the last 12 calendar months.
     (Numbers are configurable; see Q2.)
   - Only touch files matching `notes-*.db` inside the `notes_db/` family folder.
   - Never delete the newest snapshot that passed verification.
   - Local destination: unlink. Dropbox: `files_delete_v2` (recoverable from Dropbox's deleted
     files). Drop the pruned entries from the manifest.
4. **Optional JSONL export** (recommended, small): produce `notes-export-YYYYMMDD.jsonl` from
   the *verified snapshot* (never the live DB) into a `notes_export` family, same retention.
   This is a human-readable, greppable last-resort copy and supports pasting notes into other tools.
5. **Restore verification** (`restore.py`): replace `_check_notes` / `_check_notes_registry` with
   `_check_notes_db`, which opens the **newest** restored snapshot read-only, runs
   `integrity_check` and `foreign_key_check`, checks `schema_version`, and reads a sample of notes
   through `NotesStore` to prove the restored data is usable. All snapshots are still
   hash-verified when copied.
6. **Audit before coding:** read `health.py`, `recovery_drill.py`, `recovery_drill_controller.py`
   and the Dropbox restore/download path for hardcoded family names or assumptions about one
   file per family. Update them if they have any.

### 5.3 Safety rules (must hold in tests)
- The backup code never opens the live `.db` for copying and never reads `-wal` / `-shm`.
- A failed snapshot verification produces a failed run and changes nothing at either destination.
- Prune never runs on a failed or unverified upload.
- The live database's folder is not a backup destination and is not Dropbox-synced
  (extend `_validate_destination` if a check is feasible).

## 6. Phases

Each phase ends with the full test suite green.

1. **Store and schema.** `db.py`, migrations, `NotesStore` with owners, subjects, notes,
   revisions, correlations. Tests: revision chain, edit conflict, delete, subject scoping and
   duplicate rules, foreign keys, crash-safety (abort a write mid-transaction and confirm nothing
   partial), concurrent connections.
2. **Repository and writer facades.** Point `NotesRepository` / `NotesWriter` /
   `commit_revision` at the store. Port the existing shane_common notes tests (they assert
   behaviour, not file layout, so most should carry over).
3. **Registry into the DB.** `NotesRegistry` over the tables; delete the JSON file logic.
4. **App wiring.** `notes_setup.py`, browser, dock, dialogs, calories total, verse history. Fix
   whatever the existing purity_app and UI tests reveal. Remove the placeholder `notes/` folder from use.
5. **Backup snapshots.** `snapshot.py`, catalog change, retention on both destinations,
   `restore.py` DB check, audit items in 5.2(6). Update `test_catalog`, `test_restore`,
   `test_service` and the Dropbox tests; add the tests below.
6. **Export (optional).** JSONL export family and its restore check.
7. **Cleanup.** Delete dead JSONL code and docs references; add a short note to the backup docs.

## 7. Tests to add

- Snapshot is consistent while another thread writes; snapshot of an empty DB works.
- A corrupted snapshot (truncate the temp file / flip bytes) fails verification and uploads nothing.
- Unchanged DB (`write_seq` equal) makes no new snapshot and no upload; a new note does.
- Two runs on the same day create two distinct dated files; neither overwrites the other.
- Retention keeps the expected set (14 newest + monthly) and never deletes the newest good snapshot,
  including when the run that would prune failed.
- Restore of a snapshot opens with `NotesStore` and returns the expected notes, subjects, owners.
- Local and Dropbox (fake client) destinations behave the same for snapshot and prune.
- Live `.db` / `-wal` / `-shm` never appear in either destination.

## 8. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Database corruption is more severe than losing one JSONL line | WAL + `synchronous=FULL`, verified dated snapshots, optional JSONL export as an independent copy |
| Backup taken mid-write | Online backup API only; tests in 5.3 |
| Retention deletes the only good copy | Prune only after verified upload; never delete the newest verified snapshot |
| Database placed in a Dropbox-synced folder | Q1 decision; validate the path; document it |
| Schema changes later | `schema_version` plus ordered migrations from day one; snapshots record the version |
| Data not human-readable | JSONL export; browser Collection panel; any SQLite viewer |
| Threading errors | One connection per thread, created lazily; the GUI thread is the only writer today |

## 9. Open questions

- **Q1 - DB location.** Recommend `<data_root>/data/notes.db`, matching `bible_library.json` and
  `diet_state.json`, and never inside a Dropbox-synced directory. Alternative: keep it under
  `purity_app/` beside the current `notes/` folder (would need a `.gitignore` entry).
- **Q2 - Retention numbers.** Default: newest 14 plus one per month for 12 months. Adjust if you
  want fewer or more.
- **Q3 - JSONL export.** Include it (recommended) or skip it?
- **Q4 - Owner keys.** Owner keys no longer need to be safe filenames. Keep the current strict
  rules for now (less work, and useful stable slugs), or relax them to allow any printable label
  with an opaque id?
- **Q5 - `make_notes_writer(run_id=...)`.** Session run ids currently write to separate folders.
  In the database there is no per-run file. Confirm a `run_id` column on `notes` is not needed
  (recommended: drop it).

## 10. Acceptance criteria

- All note features work as they do now: journal save with owner, subject and title; edit and
  delete; browser owner/subject filtering; new owner/subject; calories total; prayer and Bible history.
- No JSONL notes files or `notes_registry.json` are read or written.
- A backup run produces a verified dated snapshot, skips when nothing changed, prunes per policy,
  and a restore drill opens the restored database and reads notes from it.
- The whole test suite passes, including the new snapshot, retention and restore tests.

## 11. Implementation notes (2026-09-29)

**Open questions - the recommended answers were taken:**
Q1 `<data_root>/data/notes.db` (resolved at import in `services/notes_setup.py` the same way
`app.main()` resolves `data_root`; the store is lazy, so importing never touches the disk).
Q2 14 newest + 12 monthly (`RetentionPolicy` defaults). Q3 JSONL export included
(`notes_export` family). Q4 owner keys keep the strict slug rules. Q5 no `run_id`
(`make_notes_writer(owner)` replaces `make_notes_writer(run_id)`).

**Deviations from the plan text:**
- `correlations` has an extra `row_ids` JSON column (a correlation's row ids are independent of its
  notes' row ids, so `correlation_notes.row_id` alone would lose information).
- `Note` and `TableNote` collapsed into one `Note` dataclass with optional table-row fields;
  `commit_v2` / `build_table_note` / `make_revision_id` are gone. Shared types live in
  `shane_common/notes/model.py`; `notes_writer` and `notes_repository` re-export the old names.
- `NotesRepository` still offers `rows_for_owner` (all revisions) + `latest_revisions()` for the
  dock/diet callers, plus `latest_notes_for_owner(..., newest_first=True)` which the browser now uses.
- A note's owner is auto-registered in `owners` on its first write, so an ad-hoc writer cannot fail
  the foreign key; subjects are *not* auto-created (an unknown subject raises `UnknownSubjectError`).
- A failed snapshot fails the **entire** run (nothing else is backed up either), as 5.2 says. Relax
  this in `BackupService.run` if you would rather back up the other families and only fail
  `notes_db`.
- The old `purity_app/notes/` folder was renamed to `notes_legacy_jsonl/` and
  `purity_app/data/notes_registry.json` to `notes_registry.json.legacy`; neither is read any more.
  Delete them once you are happy with the new system.
- The live-database-in-a-synced-folder rule is enforced as an import-time warning, not a hard
  failure: refusing to back up would remove the safety net when it is needed most. Destinations
  inside `data_root` (which contains the database folder) were already refused.
