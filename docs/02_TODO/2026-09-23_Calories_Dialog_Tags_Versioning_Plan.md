# Plan: Calories Dialog — Tags, Manual/ChatGPT Calories, Note Versioning, Retire Pulse Backfill

## Decisions confirmed with user (revised)
- **Edit = append-only versioning, not in-place rewrite.** Every new note gets
  `context["note_id"]` (stable uuid), `context["revision_num"]` (starts at 1),
  `context["op"]` ("create"). Editing an existing note commits a **new JSONL line** via the
  existing (unmodified) `NotesWriter.commit()` — same `note_id`, `revision_num + 1`, `op="edit"`,
  updated `text`/`calories`. Prior lines are never touched or deleted — this is the "lifecycle
  mechanism" the user asked for: full history retained on disk automatically, reviewable later
  (a future "view revision history" UI is explicitly out of scope for now — see below).
- **No revert mechanism yet** — user only wants the versioning/append mechanism in place now.
  Edit dialog always starts from the latest revision's content; Commit always creates a new
  revision. No "browse older revisions" or "revert" UI in this pass.
- **Previous Notes list stays as-is behaviorally**: one row per note, showing only the most
  recent revision (dedup by `note_id`, keep max `revision_num`) — no visible change in row count
  when a note has been edited multiple times.
- **No new atomic full-file-rewrite primitive needed** (this replaces the earlier "true in-place
  rewrite" plan). `rewrite_note()` is NOT being added. Edits reuse the existing, already-safe
  `NotesWriter.commit()` append path — no new primitive in shane_common's `notes_writer.py`.
- Daily total calories is **derived from notes**: sum `context["calories"]` across TODAY's Diet
  notes, **deduped to latest revision per `note_id`** first (so editing a calorie value doesn't
  double-count old + new revisions). Retires `DietState.calorie_entries` entirely (DietState
  keeps only water_count/vitamins_taken).
- "ChatGPT" button calls `estimate_calories()` **synchronously**, matching the existing
  "🍔 Test Calorie API" button pattern in `main_window.py`.
- **Backup mechanism needs NO code changes.** Editing now means *appending a line* to the note's
  JSONL file (via the same `commit()` used for new notes) — this is exactly the "legitimate
  source-side change" case the existing manifest-based `refresh_or_copy()` /
  `refresh_or_upload()` logic (in
  [local.py](../../services/backup/destinations/local.py) /
  [dropbox.py](../../services/backup/destinations/dropbox.py)) already detects and safely
  refreshes on the next backup run. No "dirty" flag exists or is needed (confirmed by audit).
  Because it's pure append (not in-place mutation), this is strictly simpler/safer for backup
  than the earlier in-place-rewrite plan.

## Phase A — shane_common: generic versioning support in the shared `NoteDialog` base
1. `shane_common/src/shane_common/notes/notes_writer.py`
   — **no changes**. `Note`/`commit()` stay exactly as-is; `note_id`/`revision_num`/`op` live
   entirely inside the existing freeform `context` dict, so no dataclass/schema change is needed.
2. `shane_common/src/shane_common/notes/notes_repository.py`
   — add small free functions (v1-safe, since v1 notes carry `note_id`/`revision_num` inside
   `context` rather than as top-level fields like v2 `TableNote` does):
   - `effective_note_id(row) -> str | None` — `row.note_id or row.context.get("note_id")`.
   - `effective_revision_num(row) -> int` — `row.revision_num or row.context.get("revision_num") or 1`.
   - `latest_revisions(rows: list[NoteRow]) -> list[NoteRow]` — groups by `effective_note_id`
     (rows without a `note_id` pass through unchanged, one per group), keeps the max
     `effective_revision_num` per group, returns sorted by `ts` descending (same order
     `_populate_history` already sorts by).
3. `shane_common/src/shane_common/ui/notes/note_dialog.py`
   — `NoteDialog` class:
   - `_on_commit`: when building `context`, inject `context.setdefault("note_id", uuid.uuid4().hex)`,
     `context["revision_num"] = 1`, `context["op"] = "create"` for brand-new notes only (additive,
     backward compatible).
   - `_populate_history()`: filter `self._history_rows` through the new
     `latest_revisions()` helper before rendering — Previous Notes continues to show one row per
     note, now correctly deduped even after edits (no visible behavior change for never-edited
     notes).
   - Add hook `_build_top_extra(self, layout) -> None` (default no-op), called at the very start
     of `_build_ui()` before the Type row — lets a subclass insert a button row (e.g. Tags).
   - Add hook `_build_commit_row_extra(self, btn_row) -> None` (default no-op), called right
     after `btn_row.addStretch()` (before `layout.addLayout(btn_row)`) — lets a subclass append
     right-anchored widgets (e.g. calories QLineEdit + ChatGPT button) onto the Commit row.
   - Add hook `_history_item_rich_text(self, row) -> str | None` (default `None`). In
     `_populate_history()`: if the hook returns non-None HTML, create the `QListWidgetItem` with
     empty text and attach a rich-text `QLabel` via `_history_list.setItemWidget(item, label)`;
     otherwise keep the existing plain-text `_format_history_item()` path. Store the source `row`
     on the item via `item.setData(Qt.ItemDataRole.UserRole, row)` in both branches (needed for
     the context menu).
   - Enable `_history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)`,
     connect to new `_on_history_context_menu(pos)`: look up the item at `pos`, read its stored
     `row`, build a `QMenu` with an "Edit" action. If `effective_note_id(row)` is `None`
     (pre-existing notes committed before this feature), show
     `QMessageBox.information(self, "Cannot Edit", "This note predates versioning and cannot be edited.")`
     instead of opening the edit dialog.
   - Add hooks for extra edit-dialog fields (all default no-ops):
     - `_extra_edit_widget_factory(self) -> QWidget | None`
     - `_extra_edit_widget_set_value(self, widget, row) -> None`
     - `_extra_edit_widget_get_context(self, widget) -> dict`
     - `_on_note_edited(self, row, new_text: str, new_context: dict) -> None`
   - Add new class `_EditNoteDialog(QtWidgets.QDialog)` in the same module: modal dialog with a
     `QPlainTextEdit` prepopulated from `row.text`, the extra widget from
     `parent_dialog._extra_edit_widget_factory()` (populated via `_extra_edit_widget_set_value`
     from the latest revision), Commit/Cancel buttons, status label. **No "Previous Notes" list
     in this dialog, no revision browser/revert UI (deferred).** On Commit: build
     `new_context = {**row.context, **parent_dialog._extra_edit_widget_get_context(widget)}`,
     then set `new_context["revision_num"] = effective_revision_num(row) + 1` and
     `new_context["op"] = "edit"` (keep the same `note_id`). Build a new `Note` via
     `parent_dialog._writer.build_note(note_type=row.note_type or NoteType.GENERAL, text=new_text, context=new_context)`
     and `parent_dialog._writer.commit(note)` — **plain append, no new primitive** — inside
     try/except (traceback + status label on failure, no silent swallow). On success: update the
     parent dialog's in-memory latest-row cache, re-render the corresponding history item,
     call `parent_dialog._on_note_edited(row, new_text, new_context)`, and `self.accept()`
     (closes Edit dialog, returns to the original dialog — original dialog is never closed).

## Phase B — purity_app: DietState & dashboard total-calories rework
*(parallel with Phase A; depends on Phase A only at final wiring/testing)*
4. `purity_app/services/diet_state.py`
   - Remove `add_calorie_entry`, `resolve_calorie_entry`, `fail_calorie_entry`,
     `pending_or_failed_entries_today`, `has_failed_entries_today`, `total_calories_today`
     (all calorie_entries machinery). Keep `_empty_day`/`get_today`/`set_water_count`/
     `set_vitamins_taken`; drop `"calorie_entries"` from the persisted schema/docstring.
   - Add a module-level pure function `calories_today_from_notes(notes_repo, owner: str = "Diet") -> float`:
     get `notes_repo.rows_for_owner(owner)`, run through the new
     `shane_common.notes.notes_repository.latest_revisions()` helper (dedup), then sum
     `row.context.get("calories")` for rows whose `row.wall_ts` falls on today's local date,
     skipping rows with no numeric `calories`.
5. `purity_app/tests/test_diet_state.py`
   - Rewrite: keep only the water/vitamins round-trip assertions; remove all calorie_entries
     assertions. Add a new test for `calories_today_from_notes()` covering the dedup-by-revision
     case (two revisions of the same note_id, same day → counted once, latest value wins).
6. `purity_app/ui/left_dock_dashboard.py` — `_DietHealthSection`:
   - Constructor: add a `notes_repo` param (imported from `services.notes_setup` at the call
     site) so `refresh()` can compute the real total.
   - `refresh()` (~line 1543): replace `self._diet_state.total_calories_today()` with
     `calories_today_from_notes(self._notes_repo)`. Replace
     `self._calories_warning_lbl.setVisible(self._diet_state.has_failed_entries_today())` with
     `self._calories_warning_lbl.setVisible(total > self._daily_calorie_budget)`.
   - Update `_calories_warning_lbl`'s tooltip (~line 1487) to something like "Exceeds your daily
     calorie budget."
   - Delete `retry_failed_calories()` method (~lines 1548-1559) — no more pulse backfill.
   - Delete the `retry_failed_diet_calories()` wrapper (~line 1818).
   - `_on_open_calories_dialog()` (~line 1510): drop `diet_state=self._diet_state` kwarg when
     constructing `CaloriesDialog`; keep `on_result_changed=self.refresh`.
   - Remove now-unused imports (`estimate_calories`, `CalorieEstimationError`, `traceback` if no
     longer used elsewhere in the file).
7. `purity_app/ui/main_window.py`
   - `_open_pulse_dialog()` (~line 1442-1444): delete the
     `self._left_dock.retry_failed_diet_calories()` call line.

## Phase C — CaloriesDialog rewrite
*(depends on Phase A hooks existing; depends on Phase B for dashboard wiring)*
8. `purity_app/ui/notes/calories_dialog.py` — rewrite:
   - Constructor: drop `diet_state` param entirely; keep `on_result_changed`/`parent`. Construct
     `self._tag_library = TagLibrary()` (from `services.tag_library`) and
     `self._selected_tags: list[str] = []`.
   - Delete `_CalorieWorker`, `self._threads`, `_start_estimate`, `_on_estimate_succeeded`,
     `_on_estimate_failed` entirely — no background thread, no auto OpenAI call on Commit.
   - Override `_build_top_extra(layout)`: small button row with a "Tags" `QPushButton` wired to
     `_open_tag_picker` (reuse `ui.left_dock_dashboard._TagPickerPopup` via direct import —
     smallest-change reuse, no relocation) plus a minimal tag-chip display row (mirrors the
     dashboard's `_rebuild_tags_display` pattern at small scale).
   - Override `_build_commit_row_extra(btn_row)`: add `self._calories_edit = QLineEdit()` (fixed
     width ~70px, `QIntValidator(0, 20000)`) and `self._chatgpt_btn = QPushButton("ChatGPT")`
     wired to `_on_chatgpt_clicked`, both appended after the stretch (right-anchored on the
     Commit row).
   - `_on_chatgpt_clicked()`: synchronous — reads `self._body_edit.toPlainText().strip()`; if
     empty, show status message and return; else call `estimate_calories(text)` in try/except
     `CalorieEstimationError` → `QMessageBox.warning(self, "Calorie Estimate Failed", str(exc))`
     (same pattern as `_test_calorie_estimate` in main_window.py); on success set
     `self._calories_edit.setText(f"{calories:.0f}")`.
   - Override `_on_commit()` (full replacement): build
     `context = {"note_id": uuid.uuid4().hex, "revision_num": 1, "op": "create"}`; if
     `self._selected_tags`: `context["tags"] = list(self._selected_tags)`; if
     `self._calories_edit.text().strip()`: `context["calories"] = float(self._calories_edit.text())`.
     Build note via `self._writer.build_note(note_type=NoteType.GENERAL, text=text, context=context)`,
     `commit()` inside try/except (unchanged error-handling shape), clear body edit and
     `self._calories_edit`, reset `self._selected_tags = []` (+ refresh tag chip row) on success,
     insert into history list (respecting rich-text hook + dedup — trivial for a brand-new note),
     call `on_result_changed()`. No DietState calls at all.
   - Override `_history_item_rich_text(row)`: if `row.context.get("calories")` is set, return
     `f"[{ts_label}] {text} - <b>{int(calories)} calories</b>"`; else fall back (`None`) to base
     formatting.
   - Override edit-hooks:
     - `_extra_edit_widget_factory()`: small `QWidget` containing a `QLineEdit` (calories) +
       `QPushButton("ChatGPT")` (re-estimate from the edit dialog's own text), consistent with
       the main row.
     - `_extra_edit_widget_set_value(widget, row)`: prefill the QLineEdit from
       `row.context.get("calories")` (latest revision's value).
     - `_extra_edit_widget_get_context(widget)`: return `{"calories": float(text)}` if non-empty
       else `{}`.
     - `_on_note_edited(row, new_text, new_context)`: call `self._on_result_changed()` (dashboard
       `refresh()` re-derives today's total from the deduped latest-revision notes — no extra
       "is this today's note" branch needed, `calories_today_from_notes()` already filters by
       date after dedup).
   - Update `setWindowTitle` and any remaining `_diet_state` references.

## Relevant files
- `shane_common/src/shane_common/notes/notes_repository.py` — add `effective_note_id`,
  `effective_revision_num`, `latest_revisions()` helpers
- `shane_common/src/shane_common/ui/notes/note_dialog.py` — hooks, context menu, `_EditNoteDialog`,
  note_id/revision_num/op injection, dedup in `_populate_history`
- `purity_app/services/diet_state.py` — retire calorie_entries, add `calories_today_from_notes()`
- `purity_app/tests/test_diet_state.py` — rewrite for new scope + dedup test
- `purity_app/ui/left_dock_dashboard.py` — `_DietHealthSection` wiring, delete pulse-retry methods
- `purity_app/ui/main_window.py` — remove pulse backfill call site
- `purity_app/ui/notes/calories_dialog.py` — full rewrite per Phase C
- `purity_app/services/tag_library.py` — reused as-is (`TagLibrary()`, no changes)
- `purity_app/services/openai_client.py` — reused as-is (`estimate_calories`, `CalorieEstimationError`)

## Verification
1. Run `purity_app` test suite (pytest, from `purity_app/` per repo memory) — confirm
   `tests/test_diet_state.py` passes and no regressions in `tests/backup/*` (untouched).
2. Manual smoke: open Calories Dialog → Tags button opens picker, create/select a tag → Commit →
   note appears in Previous Notes with bold calorie suffix once calories set.
3. Manual smoke: click ChatGPT button with sample text → lineedit populates; with `OPENAI_API_KEY`
   unset, confirm `QMessageBox.warning` appears and no crash.
4. Manual smoke: right-click a Previous Notes row → Edit → change text/calories → Commit → Edit
   dialog closes; Previous Notes still shows exactly one row for that note (now with updated
   text/calories); underlying `.jsonl` file has TWO lines for that `note_id` (revision_num 1 and
   2) — confirms append-only versioning; dashboard total updates via `on_result_changed` without
   double-counting.
5. Manual smoke: edit a note from a previous day → confirm today's dashboard total is unaffected.
6. Confirm pulse dialog no longer calls any calorie retry (grep for `retry_failed` returns no
   remaining call sites/methods).
7. Real-note backup regression check (optional but recommended): run `BackupService.run()`
   locally after editing an existing Diet note (appends a revision line), confirm `REFRESHED`
   outcome (not `DESTINATION_CONFLICT`) per the audited manifest logic — no code change expected,
   confirmation smoke test only.

## Scope boundaries (explicitly excluded)
- No changes to `RowNoteDialog`/`_NoteCard` (existing v2 revision editing for table rows) —
  untouched.
- No changes to journal/prayer/bible dialogs beyond automatically inheriting the new shared
  `NoteDialog` hooks (they get "Edit"/versioning for free with no extra fields, since their hooks
  stay default no-ops).
- **No revision-history browsing UI and no revert mechanism** in this pass — explicitly deferred
  per user. Full history is retained on disk (append-only) so a future "browse/revert" feature
  can be added later without any data migration.
- No new backup/dirty-flag code — confirmed unnecessary by audit; append-only edits are strictly
  simpler for backup than in-place rewrite would have been.
- No Windows Task Scheduler / scheduling changes.
- Old pre-existing notes (committed before this feature) have no `note_id` and simply show no
  "Edit" option (explicit message on click) — not retroactively migrated.
