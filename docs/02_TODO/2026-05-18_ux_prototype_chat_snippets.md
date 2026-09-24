# 2026-05-18 Chat Snippets: PySide6 UX Prototype

Minimum recommended chats: 4.

Why 4 chats:
- Chat 1 covers the smallest independently testable slice: models, theme, services, and the app.py entry point with a minimal main window. This validates that PySide6 launches and the fake data layer works before any complex UI is built.
- Chat 2 focuses entirely on Reflection Mode panels. This is the largest visual surface and deserves its own focused pass to iterate on layout and feel.
- Chat 3 isolates the intervention popup system. Popups are a distinct interaction paradigm and keeping them separate makes each pass reviewable without noise from the main window.
- Chat 4 builds Review Mode and wires together any remaining gaps. By this point all panels exist; this pass only assembles and polishes.

---

## Chat 1 — Foundation: models, theme, services, minimal shell

Paste this into a new chat:

```text
Implement Phase 1 and Phase 6 (app.py only, minimal main window) from [docs/TODO/2026-05-18_ux_prototype_plan.md](docs/TODO/2026-05-18_ux_prototype_plan.md).

This is a frontend-first UX prototype. No SQL, no real AI, no Chrome hooks, no real persistence.

Constraints:
- Create the full folder structure described in the plan: models/, styles/, services/, ui/, ui/widgets/, ui/reflection/, ui/intervention/, ui/review/.
- Each folder that contains Python modules needs an __init__.py.
- Implement models/journal.py, models/prayer.py, models/health.py, models/goals.py as pure dataclasses.
- Implement styles/theme.py with the full light color palette, font constants, and a global QSS stylesheet string.
- Implement services/mock_state.py (MockAppState singleton), services/fake_journal.py (FakeJournalService with seed data), services/fake_prayer.py (FakePrayerService with pool rotation), and services/fake_ai.py (FakeAIService with hardcoded outputs).
- Implement ui/widgets/card.py, stat_row.py, mood_picker.py, section_header.py.
- Replace app.py with a PySide6 entry point: QApplication, MainWindow (stub — just a titled window with the global stylesheet applied), QSystemTrayIcon placeholder, sys.exit(app.exec()). The full main window layout comes in Chat 4; for now a placeholder QLabel "Prototype loading..." in the center is enough.
- Do not implement reflection panels, intervention popups, or review mode yet.
- Do not import tkinter anywhere in new files.
- Do not import pystray in new files.

Validation:
- Run `python app.py` and confirm it launches without errors.
- Confirm the window title is visible and the stylesheet is applied (background color visible).
- Provide a concise summary of what was created, what is still stub/placeholder, and any issues found.
```

---

## Chat 2 — Reflection Mode panels

Paste this into a new chat after Chat 1 is complete:

```text
Implement Phase 3 (all reflection panels) from [docs/TODO/2026-05-18_ux_prototype_plan.md](docs/TODO/2026-05-18_ux_prototype_plan.md).

Context:
- Chat 1 already created models/, styles/theme.py, services/, and ui/widgets/.
- Read those files before writing any reflection panel code so widget usage is consistent.

Constraints:
- Implement all files in ui/reflection/: journal_panel.py, prayer_widget.py, health_widget.py, goals_widget.py, encouragement_widget.py, streak_widget.py, dashboard.py.
- journal_panel.py must have 3 working tabs: Guided Check-In (3 questions + Save), Free Journal (text area + Save), History (updates after Save).
- prayer_widget.py must show one person at a time with progress indicator; "I Prayed" and "Skip for now" must both update the display correctly.
- health_widget.py reads from MockAppState and color-codes values.
- dashboard.py assembles all panels into a 3-column layout with QScrollArea per column.
- Connect dashboard.py into the MainWindow stub (replace the "Prototype loading..." placeholder with the ReflectionDashboard).
- Do not implement intervention popups or review mode yet.
- Do not add new dependencies beyond PySide6.

Validation:
- Run `python app.py` and confirm the Reflection Mode dashboard renders with all panels visible.
- Confirm journal Save works and History tab updates.
- Confirm prayer "I Prayed" advances correctly.
- Confirm health metrics display with color coding.
- Provide a concise summary of what was implemented and any UX decisions made during layout.
```

---

## Chat 3 — Intervention popup system

Paste this into a new chat after Chat 2 is complete:

```text
Implement Phase 4 (intervention popup system) from [docs/TODO/2026-05-18_ux_prototype_plan.md](docs/TODO/2026-05-18_ux_prototype_plan.md).

Context:
- Chats 1 and 2 already created the foundation and reflection panels.
- Read ui/widgets/card.py and styles/theme.py before writing popup code.

Constraints:
- Implement all files in ui/intervention/: base_popup.py, chrome_popup.py, prayer_popup.py, risk_popup.py, hourly_popup.py, evening_popup.py, popup_manager.py.
- base_popup.py must center itself on screen and apply the theme stylesheet.
- Each popup must be self-contained: it can be shown independently without the main window being visible.
- popup_manager.py must prevent multiple instances of the same popup type from opening simultaneously (check isVisible()).
- Add a demo sidebar to MainWindow: a vertical QGroupBox labeled "Demo Triggers" with one QPushButton per popup type ("Fire: Chrome", "Fire: Prayer", etc.) plus an "Open Review" stub button. The sidebar sits on the right edge of the main window.
- Wire each button to popup_manager.trigger(popup_type).
- Do not implement review mode yet ("Open Review" button can show a placeholder QMessageBox).
- Popups must dismiss cleanly (no dangling windows or Qt warnings).

Validation:
- Run `python app.py` and confirm the demo sidebar is visible.
- Fire all 5 popup types and confirm each appears centered, styled, and dismisses without error.
- Confirm that clicking the same popup button twice while one is open does not open a second instance.
- Provide a concise summary of popup interactions and any emotional-tone decisions made during implementation.
```

---

## Chat 4 — Review Mode and final assembly

Paste this into a new chat after Chat 3 is complete:

```text
Implement Phase 5 (review mode) and finalize Phase 6 (main window assembly) from [docs/TODO/2026-05-18_ux_prototype_plan.md](docs/TODO/2026-05-18_ux_prototype_plan.md).

Context:
- Chats 1–3 already created all foundation, reflection panels, and intervention popups.
- Read the current ui/main_window.py and services/fake_ai.py before writing review code.

Constraints:
- Implement ui/review/weekly_summary.py, ui/review/trend_cards.py, ui/review/review_window.py.
- review_window.py must show: header with date range, WeeklySummaryWidget, TrendCardsWidget, encouragement/suggestions section, and a Close button.
- Wire the "Open Review" button in the demo sidebar to open ReviewWindow (replace the placeholder QMessageBox).
- Add the header bar to MainWindow: app name ("Purity"), current time updated by QTimer every 60s, today's streak badge, and a brief verse snippet. The header sits above the main layout.
- Polish pass: verify consistent spacing, font sizes, and card padding across all panels using the theme constants. Fix any obvious visual inconsistencies.
- Do not add new dependencies.
- Do not implement backend systems.

Validation:
- Run `python app.py` and verify the full prototype is functional end-to-end:
  1. Header bar shows time and streak.
  2. Reflection dashboard renders with all panels.
  3. Journal save → History tab updates.
  4. Prayer "I Prayed" advances queue; pool resets after all 10.
  5. All 5 popups fire and dismiss cleanly.
  6. Review window opens with fake weekly data.
- Run through the full verification checklist in the plan file.
- Provide a concise summary of what was implemented, any deferred items, and recommended next UX iteration areas.
```
