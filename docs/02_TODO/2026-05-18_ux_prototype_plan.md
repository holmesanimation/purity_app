# 2026-05-18 Plan: PySide6 UX Prototype

Build a frontend-first interactive prototype for the Purity App using PySide6. The goal is UX exploration, layout validation, emotional tone testing, and interaction flow prototyping — NOT a production implementation pass.

## Decisions

- **Framework**: PySide6 6.9.1 / Python 3.11
- **Theme**: Light — off-white (#FAF9F6), warm beige (#F5F0E8), charcoal text (#2D2926), warm muted accents
- **Popup triggers**: Demo sidebar panel with manual fire buttons (no auto-timers)
- **Entry point**: `app.py` is replaced entirely with the PySide6 prototype
- **Existing files**: `reminder_dialog.py`, `chrome_dialog.py`, `focus_guard.py`, `focus_guard_chrome_trigger.py` are left untouched
- **Tray icon**: `QSystemTrayIcon` placeholder only — no `pystray` in prototype
- **Backend**: Entirely mock/fake/in-memory — no SQL, no real AI, no Chrome process hooks, no real persistence
- **Scope boundary**: `shane_common` is still imported for existing utilities only; new prototype code does NOT add new `shane_common` dependencies

## Folder Structure

```
purity_app/
    app.py                              ← REPLACED — PySide6 QApplication entry point

    ui/
        main_window.py                  ← QMainWindow shell; header bar, 3-column layout, demo sidebar
        reflection/
            __init__.py
            dashboard.py               ← Assembles the full reflection layout
            journal_panel.py           ← QTabWidget: Guided Check-In / Free Journal / History
            prayer_widget.py           ← PrayerMate card (one person at a time)
            health_widget.py           ← Fake health metrics (sleep, hydration, workout, protein)
            goals_widget.py            ← Goals/commitments card with checkboxes
            encouragement_widget.py    ← Daily verse + encouragement card
            streak_widget.py           ← Purity streak + focus state badges
        intervention/
            __init__.py
            base_popup.py              ← Base QDialog: centered, soft-styled, small footprint
            chrome_popup.py            ← "Why are you opening Chrome?"
            prayer_popup.py            ← "Pray for [Name]" with I Prayed / Skip
            risk_popup.py              ← Dopamine/risk state warning card
            hourly_popup.py            ← Hourly check-in with mood picker
            evening_popup.py           ← Evening shutdown checklist
            popup_manager.py           ← trigger(popup_type) dispatch; single-instance per type
        review/
            __init__.py
            review_window.py           ← Full review/report QDialog
            weekly_summary.py          ← Weekly summary section widget
            trend_cards.py             ← Trend + category card widgets
        widgets/
            __init__.py
            card.py                    ← Styled QFrame base card (soft shadow, rounded corners)
            stat_row.py                ← Label + value metric row
            mood_picker.py             ← Emoji mood selector button row
            section_header.py          ← Styled section title label

    services/
        __init__.py
        mock_state.py                   ← Central fake state singleton (streak, sleep, hydration, verse, risk, etc.)
        fake_ai.py                      ← Hardcoded AI report strings, category analysis, weekly reflection
        fake_journal.py                 ← In-memory journal store with 5–8 seed entries
        fake_prayer.py                  ← Pool-based prayer rotation (refills when pool exhausted)

    models/
        __init__.py
        journal.py                      ← JournalEntry dataclass
        prayer.py                       ← PrayerPerson dataclass
        health.py                       ← HealthMetrics dataclass
        goals.py                        ← Goal dataclass

    styles/
        __init__.py
        theme.py                        ← Color palette constants, font constants, global QSS stylesheet string
```

## Implementation Phases

### Phase 1 — Foundation
Build in parallel; no inter-dependencies.

1. **`models/`** — pure dataclasses (no methods, no logic)
   - `JournalEntry(id, timestamp, entry_type, responses, free_text)`
   - `PrayerPerson(id, name, notes)`
   - `HealthMetrics(sleep_hours, hydration_glasses, hydration_target, workout_done, protein_g, protein_target, caffeine_cups)`
   - `Goal(id, title, why, daily_actions, completed_today)`

2. **`styles/theme.py`** — all visual constants in one file
   - Color palette (background, surface, text, muted, accent, success, warning, danger)
   - Font definitions
   - Global QSS stylesheet string (cards, buttons, tabs, labels, text inputs)

3. **`services/mock_state.py`** — singleton `MockAppState` class
   - Purity streak, sleep hours, hydration, energy level
   - Today's verse (reference + text)
   - Risk level (low / medium / high)
   - Today's goals list
   - Last check-in mood
   - Current focus state label

4. **`services/fake_journal.py`** — `FakeJournalService`
   - 5–8 pre-seeded `JournalEntry` objects
   - `append(entry)` method stores in a list
   - `get_all()` returns entries newest-first

5. **`services/fake_prayer.py`** — `FakePrayerService`
   - Pool of ~10 `PrayerPerson` objects
   - `current()` → current person
   - `mark_prayed()` → removes from pool, refills + reshuffles if empty
   - `skip()` → defers without removing
   - `progress()` → (prayed_count, total_count)

6. **`services/fake_ai.py`** — `FakeAIService`
   - Hardcoded weekly report string
   - `get_categories()` → list of (category, count) pairs
   - `get_suggestions()` → list of suggestion strings
   - `get_encouragement_insight()` → single string

### Phase 2 — Base Widgets
Depends on Phase 1 (theme).

7. **`widgets/card.py`** — `CardWidget(QFrame)`: styled surface, optional title label, `body_layout` for child widgets

8. **`widgets/stat_row.py`** — `StatRow(QWidget)`: label + value + optional status icon in a horizontal row

9. **`widgets/mood_picker.py`** — `MoodPicker(QWidget)`: row of emoji buttons (😊 😐 😞 😣), emits `mood_selected(str)` signal

10. **`widgets/section_header.py`** — `SectionHeader(QLabel)`: bold, slightly larger, with bottom border or spacing

### Phase 3 — Reflection Panels
Depends on Phases 1–2. Build in parallel.

11. **`reflection/journal_panel.py`** — `JournalPanel(QWidget)`
    - Tab 1: Guided Check-In — 3 text areas with questions, Save button, saves `JournalEntry(entry_type="guided_checkin")`
    - Tab 2: Free Journal — single text area, timestamp label, Save button
    - Tab 3: Journal History — `QListWidget` or scroll area showing past entries; updates on save

12. **`reflection/prayer_widget.py`** — `PrayerWidget(CardWidget)`
    - Name label, optional notes label
    - Progress indicator (e.g., "3 of 10 prayed today")
    - "I Prayed" button → `mark_prayed()` → refresh display
    - "Skip for now" button → `skip()` → refresh display

13. **`reflection/health_widget.py`** — `HealthWidget(CardWidget)`
    - `StatRow` per metric: Sleep, Hydration, Workout, Protein, Caffeine
    - Reads from `MockAppState`
    - Color-codes values (green/orange/red) based on thresholds

14. **`reflection/goals_widget.py`** — `GoalsWidget(CardWidget)`
    - Checkbox list of today's goals from `MockAppState`
    - Toggle updates state in memory

15. **`reflection/encouragement_widget.py`** — `EncouragementWidget(CardWidget)`
    - Verse reference (small, muted) + verse text (readable, centered)
    - Short encouragement line below
    - "New verse" button cycles through fake verse list

16. **`reflection/streak_widget.py`** — `StreakWidget(QWidget)`
    - Streak counter badge (e.g., "Day 12")
    - Focus state label (e.g., "🟢 Strong state" / "⚠️ Elevated risk")
    - Reads from `MockAppState`

17. **`reflection/dashboard.py`** — `ReflectionDashboard(QWidget)`
    - Three-column layout via `QHBoxLayout`
    - Left: `StreakWidget` + `HealthWidget` + `GoalsWidget`
    - Center: `JournalPanel` + `EncouragementWidget`
    - Right: `PrayerWidget` + risk summary card (static fake data)
    - Each column wrapped in `QScrollArea`

### Phase 4 — Intervention Popup System
Depends on Phase 2 (base widgets + theme).

18. **`intervention/base_popup.py`** — `BasePopup(QDialog)`
    - Fixed small size (~380×280 typical)
    - Centered on screen
    - Soft beige background, subtle border
    - `title_label`, `body_layout` area, standard button row
    - `show_centered()` helper

19. **`intervention/chrome_popup.py`** — `ChromePopup(BasePopup)`
    - "You opened Chrome. Why?" heading
    - 5 choice buttons: Work / Research / Entertainment / Bored / I don't know
    - Each choice dismisses popup; "Bored" / "I don't know" shows a brief redirect message

20. **`intervention/prayer_popup.py`** — `PrayerPopup(BasePopup)`
    - "🙏 Pray for: [Name]" heading
    - Short textbox: "What's on your mind?"
    - `MoodPicker` row
    - "I Prayed" + "Remind me later" buttons

21. **`intervention/risk_popup.py`** — `RiskPopup(BasePopup)`
    - Risk state header ("⚠️ High Risk State" or "🟢 Strong State")
    - Bullet list of contributing factors (fake)
    - Recovery action suggestion (fake)
    - "I understand" dismiss button

22. **`intervention/hourly_popup.py`** — `HourlyPopup(BasePopup)`
    - "Quick check-in" heading
    - `MoodPicker`
    - Short text prompt: "What are you working on?"
    - Submit + Dismiss

23. **`intervention/evening_popup.py`** — `EveningPopup(BasePopup)`
    - "🌙 Night Reset" heading
    - Checklist of shutdown steps (static checkboxes)
    - "All done" dismiss button

24. **`intervention/popup_manager.py`** — `PopupManager`
    - Registry: `{popup_type: popup_class}`
    - `trigger(popup_type: str)` — instantiates and `show_centered()` the popup
    - Prevents multiple instances of same type (checks `isVisible()`)

### Phase 5 — Review Mode
Depends on Phases 1–2. Build in parallel with Phase 4.

25. **`review/weekly_summary.py`** — `WeeklySummaryWidget(QWidget)`
    - Summary stats row: clean days, journal entries, prayer completions
    - Top themes list from `FakeAIService.get_categories()`
    - Plain text AI reflection paragraph

26. **`review/trend_cards.py`** — `TrendCardsWidget(QWidget)`
    - Row of small cards showing fake trend data (temptation frequency, sleep average, mood trend)

27. **`review/review_window.py`** — `ReviewWindow(QDialog)`
    - Header: "Weekly Review — [date range]"
    - `WeeklySummaryWidget`
    - `TrendCardsWidget`
    - Encouragement/suggestions section from `FakeAIService.get_suggestions()`
    - Close button

### Phase 6 — Assembly
Depends on all previous phases.

28. **`ui/main_window.py`** — `MainWindow(QMainWindow)`
    - Header bar: app name, current time (`QTimer` updates every 60s), streak badge, verse snippet
    - Central area: `QSplitter` or `QHBoxLayout` with `ReflectionDashboard` (left+center) and demo sidebar (right)
    - Demo sidebar (`QGroupBox`): "Fire Popup" buttons for each of the 5 popup types; "Open Review" button
    - Navigation: tab strip or top buttons for Reflection / Review modes
    - `PopupManager` instance stored on window

29. **`app.py`** — replacement entry point
    - `QApplication` setup with global stylesheet from `theme.py`
    - Instantiate `MainWindow`, show, center on screen
    - `QSystemTrayIcon` placeholder (no menu, just icon presence)
    - `sys.exit(app.exec())`

## Verification Checklist

1. `python app.py` — PySide6 window opens without errors or warnings
2. All 5 popup types fire from demo sidebar buttons, appear centered, and dismiss cleanly
3. Journal Guided Check-In: fill in 3 questions → Save → entry appears in History tab
4. Prayer queue: "I Prayed" advances to next person; after all 10 are prayed for, pool resets
5. "Open Review" button opens the review window with fake weekly data
6. Free Journal: type text → Save → entry appears in History tab
7. Goals checkboxes toggle without errors
8. "New verse" button in encouragement widget cycles verses
9. No `import tkinter` in any new file
10. No SQL, no file I/O, no network calls in any new file

## Explicit Non-Scope

- No SQL or real persistence
- No real AI / LLM calls
- No Chrome process monitoring or window disabling
- No `pystray` tray icon menu (placeholder `QSystemTrayIcon` only)
- No `shane_common` new integrations (existing imports in unchanged files are fine)
- No user authentication or multi-user support
- No notification services or external messaging
- No auto-timers for popup triggers (demo sidebar only)
- No production event logging

## Dependencies

Already installed: `PySide6==6.9.1`, `Python 3.11.4`

No additional dependencies required for the prototype.
