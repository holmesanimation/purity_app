# Plan: WebPopup Redesign

## Status
- COMPLETE
- Created: 2026-06-09
- Completed: 2026-06-09

## Decisions
- Implement the redesign in d:\code\git\purity_app\ui\intervention\web_popup.py
- Use d:\code\git\purity_app\ui\intervention\web_popup copy.py as reference only; do not modify it
- Keep Chrome launch ownership in d:\code\git\purity_app\ui\main_window.py
- Keep blocked-browser behavior unchanged unless the redesign requires a minimal compatibility fix
- Do not widen scope to queued request plumbing or browser session manager behavior beyond the WebPopup contract

---

## Goal
Replace the live permitted WebPopup dialog with a PanicReasonDialog-inspired layout that collects feelings, purpose text, and session duration, then returns Accepted so MainWindow continues to start the browser session and launch Chrome where it already does.

## Phase 1: Preserve the owning flow
**Files**:
- d:\code\git\purity_app\ui\main_window.py
- d:\code\git\purity_app\ui\intervention\web_popup.py

- Keep WebPopup responsible only for collecting result fields and calling accept()
- Keep Chrome launch and browser-session startup in MainWindow._on_web_opened() and MainWindow._handle_web_launch_request()
- Preserve the existing result contract read by MainWindow:
  - selected_choice
  - reason_text
  - allowed_urls
  - duration_seconds
  - selected_feelings

## Phase 2: Rebuild the permitted WebPopup layout
**Files**:
- d:\code\git\purity_app\ui\intervention\web_popup.py
- Reference: d:\code\git\purity_app\ui\intervention\panic_reason_dialog.py
- Reference only: d:\code\git\purity_app\ui\intervention\web_popup copy.py

- Rework the permitted flow in WebPopup to follow the vertical structure and styling patterns used in PanicReasonDialog
- Use a full-width feelings reveal button followed by a 2-column feelings grid
- Keep the reminder / encouragement section aligned with the newer dialog direction shown in the reference copy
- Preserve the blocked-browser layout separately

## Phase 3: Add the requested internet-session controls
**File**: d:\code\git\purity_app\ui\intervention\web_popup.py

- Below the feeling buttons, add the purpose title label
- Add the purpose QTextEdit below that
- Add the time label and duration combo below the purpose text
- Add the commit button below the time row
- Keep commit gating tied to the purpose text and the intended WebPopup requirements

## Phase 4: Keep the result model stable
**File**: d:\code\git\purity_app\ui\intervention\web_popup.py

- Continue setting selected_choice to internet_session on commit
- Continue using allowed_urls = [] unless scope intentionally changes later
- Copy the selected feelings set into the public selected_feelings list during commit
- Store the trimmed purpose text in reason_text
- Store the selected combo value in duration_seconds
- Call accept() so the existing MainWindow flow remains intact

## Phase 5: Remove or isolate obsolete permitted-flow pieces
**File**: d:\code\git\purity_app\ui\intervention\web_popup.py

- Remove or isolate the older choice-button permitted flow if it becomes dead code after the redesign
- Remove or isolate legacy helpers that only supported the prior two-step choice + URL flow
- Leave blocked-browser behavior intact
- Only touch d:\code\git\purity_app\ui\intervention\web_popup copy.py as a visual / behavior reference

---

## Verification
1. Run a focused syntax or narrow project check covering d:\code\git\purity_app\ui\intervention\web_popup.py.
2. Run or update the narrowest tests covering WebPopup commit enablement and returned fields.
3. Manually verify the browser watcher flow: open Chrome directly, confirm the redesigned popup appears, commit, and confirm browser session state starts.
4. Manually verify the queued launcher flow: confirm Commit returns Accepted and MainWindow launches Chrome afterward.

## Notes
- Existing tests in d:\code\git\purity_app\tests\test_web_popup.py likely target the older choice-based popup flow and may need to be updated as part of this slice.
- PySide import-resolution diagnostics in the editor appear environment-related; prefer runtime syntax checks and targeted execution for validation.
