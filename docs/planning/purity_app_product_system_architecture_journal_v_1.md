# Purity App — Product Vision, Systems Architecture, and Rolling Development Journal

## Overview

The Purity App is evolving from a simple anti-distraction / anti-porn interruption tool into a broader:

- discipline reinforcement system
- nervous-system awareness system
- health and formation system
- spiritual accountability system
- purpose alignment system
- intentionality reinforcement tool

The app should help users:

- build self-control
- improve health
- align daily behavior with long-term goals
- reduce impulsive behavior
- identify recurring temptation patterns
- reinforce discipline and intentionality
- improve sleep, energy, hydration, and focus
- develop stronger habits and routines

The app should not merely punish or block behavior.

It should:

- redirect
- reframe
- reveal patterns
- support recovery
- reinforce purpose

---

# Existing System Foundations

Current app capabilities already include:

- reset popup system
- hydration tracking
- vitamin tracking
- temptation self-reporting
- energy self-reporting
- belief journaling
- scripture matching
- Chrome interruption dialogs
- enforced reset timers
- JSONL event logging
- configurable belief/scripture mapping
- tray app integration
- Chrome process monitoring

These existing systems provide the foundation for a larger personal formation platform.

---

# Core Product Direction

## Reframe Purity as Formation

The app should connect purity with:

- strength
- clarity
- discipline
- sleep quality
- energy
- masculinity
- focus
- mission
- calling
- future identity

Instead of:

"Don’t fail."

The app should communicate:

"Become the kind of man you want to be."

---

# Proposed Systems

# 1. Mission Status / Daily State Dashboard

Potential popup section:

```text
⚔️ TODAY'S MISSION

Sleep:      6h 12m ❌
Hydration:  5/8 by now ⚠️
Protein:    92g / 180g
Workout:    Not completed
Creatine:   Missed
Caffeine:   3 cups ❌
Purity:     Clean today ✅
```

Purpose:

- connect temptation to nervous system state
- externalize dysregulation
- reinforce discipline momentum
- encourage holistic formation

---

# 2. Temptation as Recovery Diagnostic

Current app already records:

- energy
- temptation
- beliefs

Additional useful inputs:

- sleep duration
- caffeine intake
- workout completion
- protein intake
- isolation level
- boredom
- emotional state

Potential future correlations:

```text
Temptation spikes:
- sleep < 6.5h
- caffeine > 3
- no lifting
- low hydration
- boredom after 9pm
```

This transforms the app into:

- a purity journal
- a nervous-system journal
- a behavioral telemetry system

---

# 3. Dopamine State Warnings

Example:

```text
⚠️ HIGH RISK STATE

- Slept 5h 40m
- 4 coffees consumed
- No workout today
- Alone at home
- Chrome opened after 10pm
```

Or:

```text
🟢 STRONG STATE

- Slept 8h
- Lifted weights
- Hydrated
- Low temptation
- Purposeful work completed
```

Goal:

- make temptation predictable
- separate identity from state
- reinforce awareness

---

# 4. Future Self System

Potential prompts:

```text
If you stay disciplined tonight:

+ Better sleep quality
+ Better confidence tomorrow
+ Better trading focus
+ Better energy
+ Better future husband/father energy
```

Messages should dynamically adapt based on:

- sleep
- lifting consistency
- purity streak
- late-night browsing
- hydration
- emotional state

---

# 5. Manhood Metrics

Potential dashboard:

```text
⚔️ Masculine Health

Sleep consistency: 72%
Strength sessions this week: 1/2
Protein target: 68%
Water target: 55%
Creatine: ✅
Zinc-rich foods: ❌
Screen discipline: ⚠️
```

Purpose:

Shift framing from:

- avoiding failure

to:

- building strength

---

# 6. Evening Shutdown Flow

Potential nightly reset:

```text
🌙 NIGHT RESET

- No more caffeine
- No YouTube wandering
- Dim lights
- Prepare for sleep
- Tomorrow’s market prep complete?
- Did you pray?
```

Potential future behavior:

- stronger Chrome restrictions after 10pm
- longer cooldowns
- more aggressive interruption flows

---

# 7. Purpose and Direction Questions

Potential prompts:

```text
What meaningful thing are you building right now?
What would make today feel purposeful?
What are you avoiding emotionally?
```

These may become among the most transformative aspects of the system.

---

# 8. Expanded Belief Mapping

Current system maps:

- shame
- weakness
- escape
- hidden sin

Potential future beliefs:

- “I’ll start tomorrow.”
- “Sleep doesn’t matter.”
- “I need stimulation.”
- “One night won’t matter.”
- “Discipline won’t change anything.”

Responses could include:

- scripture
- encouragement
- identity reminders
- health reminders
- mission reminders

---

# 9. Recovery Action Generator

Potential adaptive response system:

```text
You reported:
- low energy
- high temptation
- poor sleep

Recommended reset:
1. 20oz water
2. 10 pushups
3. leave computer for 5 minutes
4. no caffeine now
5. lights dimmed after 10pm
```

---

# 10. Chrome Health Intercepts

Current Chrome flow already asks:

"Why are you opening the browser?"

Potential upgraded flow:

```text
You slept 5h 40m last night.
High dopamine-seeking risk detected.

What do you actually need right now?

[Rest]
[Water]
[Connection]
[Purpose]
[Actual task]
```

---

# Goals System

## Vision

Add a configurable goals system that informs:

- future self prompts
- encouragement messages
- browser reminders
- nightly review prompts
- recovery suggestions

Potential goals:

```text
- Become sexually pure and self-controlled
- Sleep by 10pm
- Build trading platform discipline
- Lift weights 2x/week
- Eat around 2200 calories/day
- Grow in prayer and Scripture
```

Potential goal schema:

```json
{
  "id": "sleep_consistency",
  "title": "Sleep by 10pm",
  "why": "Better energy, discipline, testosterone, trading focus",
  "daily_actions": [
    "Shutdown by 9:30pm",
    "No caffeine after 10am"
  ],
  "encouragements": [
    "Future you wakes up stronger when present you shuts down on time."
  ]
}
```

---

# Meals and Nutrition System

## Initial Direction

Start simple.

Do NOT begin with automatic calorie APIs.

V1 should focus on:

- meal journaling
- nutrition awareness
- end-of-day export summaries

Potential UI:

```text
Breakfast:
- 2 eggs
- toast
- coffee

Lunch:
- chicken rice bowl
- pumpkin seeds

Dinner:
- beef, sweet potato, kale

Snacks:
- protein shake
```

Potential export summary:

```text
MyFitnessPal Summary

Breakfast:
...

Estimated goals:
- Calories target: ~2200
- Protein target
- Fibre goal: 10g per meal
- Hydration: 100–110oz
- Notes: caffeine after 10am?
```

Future possibility:

- calorie APIs
- nutrition estimation
- macro tracking

---

# Chrome Gate System

## Current State

Current Chrome dialog already:

- intercepts Chrome opening
- asks intent
- blocks wandering categories
- closes browser in some cases

## Proposed Upgrade

Potential flow:

```text
Why are you opening Chrome?

[Actual task]
[Waiting]
[Bored]
[Tempted]
[Escaping]
```

Unlock requirements:

```text
1. Describe your task.
2. Fill in a Bible verse.
```

Example:

```text
“Create in me a _____ heart, O God.”
```

Potential policy:

- Need / Actual task:
  - allow Chrome
  - enable reminder overlay

- Bored / Waiting / Escaping:
  - stronger reset flow
  - optional browser close
  - log event

---

# Floating Chrome Reminder

## Purpose

The danger is often not opening Chrome.

The danger is:

- wandering
- drifting
- losing intentionality

Potential reminder:

```text
Chrome is open for:
“Check broker docs”

Stay on mission.
No wandering.
Close Chrome when done.

[Done]
```

Potential future additions:

- timeout detection
- idle detection
- task completion reminders

---

# Review / Feedback System

## Vision

The app should support ongoing iteration.

The user should be able to provide:

- frustrations
- insights
- feature ideas
- temptation observations
- habit observations
- emotional observations

Potential prompts:

```text
What helped today?
What felt annoying?
What did the app miss?
What temptation pattern did you notice?
What should the app remind you of tomorrow?
```

Potential storage:

```json
{
  "timestamp": "...",
  "type": "user_feedback",
  "context": "evening_review",
  "helpful": "The Chrome verse gate helped.",
  "annoying": "Water requirement blocked me too aggressively.",
  "request": "Remind me about sleep earlier."
}
```

This system becomes foundational for:

- future app refinement
- tailoring to other users
- experimentation
- feature iteration

---

# Accountability Notification System

## Core Idea

```text
Risk signals → notification policy → grace delay → optional prayer request
```

Potential risk triggers:

- Chrome opened after 10pm
- repeated Chrome attempts
- high temptation slider
- low energy + high temptation
- boredom / escaping states
- manual prayer request

## Important Product Decision

The system should begin manual-first.

NOT automatic-first.

Recommended v1 behavior:

```text
High-risk state detected.
Would it help to ask for prayer?

[Send prayer request]
[Not now]
[Remind me later]
```

Also include:

```text
🙏 Ask for prayer now
```

Important safeguards:

- avoid explicit browsing details
- cooldowns
- logging
- optional disable
- configurable contacts

Potential message:

"Hey, could you pray for me right now? I’m trying to choose discipline and purity."

---

# Rolling Documentation System

## Recommended Folder Structure

```text
purity_app/
    docs/
        00_product_vision.md
        01_core_principles.md
        02_feature_backlog.md
        03_experiments.md
        04_daily_learnings.md
        05_architecture.md
        06_notification_policy.md
        07_goal_system.md
        08_health_system.md
        09_chrome_gate_system.md
```

## Most Important Document

Create:

```text
purity_app/docs/purity_app_journal.md
```

Use it as:

- rolling idea capture
- insight journal
- feature brainstorm
- design evolution log
- temptation pattern log
- product research notebook

---

# Recommended Documentation Patterns

## Problem → Insight → Mechanism

Example:

```markdown
Problem:
User drifts after opening Chrome for legitimate reasons.

Insight:
The danger is not opening Chrome — it is loss of intentionality.

Mechanism:
Persistent floating reminder showing:
- why Chrome was opened
- active goals
- close browser reminder
```

---

# Feature Status Labels

Recommended statuses:

```text
IDEA
THINKING
PLANNED
IN PROGRESS
TESTING
KEPT
REMOVED
FAILED
```

---

# Experiment Logging

Example:

```markdown
## Chrome Scripture Fill-In

Mechanism:
Require Bible verse completion before Chrome unlock.

Result:
- interrupts impulsive opening
- forces awareness
- may become annoying if overused

Ideas:
- randomize verses
- contextual verses
- easier work-hour mode
```

---

# Shared Common Package Direction

## Recommended Structure

```text
git/
  purity_app/
  shane_common/
  trading_platform/
```

Current temporary exception: trading_platform is still running from `D:\code\git` and should be treated that way until its files are moved into `D:\code\git\trading_platform`.

## Purpose

Create reusable generic infrastructure shared between apps.

Do NOT share trading-specific systems.

Share only reusable primitives.

---

# Recommended Shared APIs

Potential shared modules:

```text
shane_common/
  events/
  telemetry/
  config/
  notifications/
  ui/
  experiments/
  db/
```

Potential reusable features:

- event logging
- JSONL persistence
- config management
- notifications
- supervisor/heartbeat
- feedback stores
- dashboards
- experiment logging

---

# Important Architectural Principle

Dependency direction:

```text
trading_platform  → shane_common
purity_app        → shane_common
shane_common      → neither app
```

Key rule:

Extract only after both apps genuinely need the abstraction.

---

# Shared SQL Layer

## Recommendation

Create:

```text
shane_common/db/
```

Use:

- SQLite initially
- simple repository layer
- sqlite3 + dataclasses

Avoid full ORM initially.

Potential databases:

```text
C:/TP_DATA/trading_platform.db
~/.purity_app/purity_app.db
```

---

# Recommended Shared Tables

Potential generic tables:

```sql
CREATE TABLE app_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE feedback_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    category TEXT,
    body TEXT NOT NULL,
    status TEXT DEFAULT 'new',
    payload_json TEXT
);

CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    channel TEXT NOT NULL,
    recipient TEXT,
    subject TEXT,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT
);
```

---

# SQL vs JSONL Philosophy

## JSONL

Keep JSONL for:

- audit logs
- event streams
- replay-style telemetry
- append-only journaling

## SQL

Use SQL for:

- querying
- feedback
- goals
- notifications
- reviews
- summaries
- configuration
- experiments index

---

# Final Product Philosophy

The Purity App should become:

- a discipline companion
- a formation system
- a nervous-system awareness tool
- a health alignment tool
- a mission reinforcement system
- an intentionality engine

It should help users:

- understand patterns
- redirect impulses
- reinforce purpose
- strengthen discipline
- improve health
- align daily behavior with long-term identity

Rather than merely:

- blocking websites
- enforcing shame
- punishing failure

The app should cultivate:

- awareness
- clarity
- intentionality
- resilience
- consistency
- formation

---

# Architecture Update — Reflection Mode, Intervention Mode, Journal System, PrayerMate (2026-05-18)

## Evolving Product Direction

The app is evolving away from being a simple "focus tool" and toward becoming a:

- spiritual dashboard
- reflection/journaling system
- prayer system
- accountability system
- goals tracker
- emotional awareness system
- intervention platform
- AI-assisted personal operating dashboard

The architecture should favor:
- one unified shell
- multiple integrated modules/panels
- shared AI/reporting backend
- centralized event + state pipeline

NOT multiple disconnected mini-apps.

---

# High-Level GUI Direction

## Two Main GUI Experiences

### 1. Reflection Mode (Landing Page)

Purpose:
- intentional engagement
- grounding/orienting the day
- journaling
- prayer
- reviewing reports/trends
- planning
- reflection

This is the primary dashboard experience and the "home base" of the application.

This mode should feel:
- calm
- spacious
- intentional
- personalized
- encouraging
- reflective

Conceptual layout:

```text
+--------------------------------------------------+
| Header                                           |
| Time | Verse | Streaks | Focus State             |
+--------------------------------------------------+

| Left Column            | Center                |
|-------------------------|----------------------|
| Prayer Queue            | Journal Panel        |
| Daily Check-In          | Free Writing         |
| Goals                   | AI Reflections       |
| Mood                    | Reports              |
|-------------------------|----------------------|

| Right Column                                   |
|------------------------------------------------|
| Focus Guard Status                              |
| Temptation Risk Indicators                      |
| Chrome Intent Prompt                            |
| Notifications / Encouragement                   |
| Active Commitments                              |
+--------------------------------------------------+
```

### 2. Intervention Mode (Popup System)

Purpose:
- interrupt autopilot
- redirect attention
- quick awareness check
- lightweight accountability
- gather emotional/spiritual signals

This mode should feel:
- concise
- frictionless
- non-punitive
- lightweight
- gentle
- actionable

Typical interaction duration: 15–45 seconds. This is NOT for deep journaling.

Example popup (prayer prompt):

```text
🙏 Pray for: Mike
[✓ I prayed]

What's on your mind?
[ short textbox ]

How are you doing?
🙂 😐 😞 😣

[Submit]
[Remind me later]
```

Example popup (Chrome intent):

```text
You opened Chrome.
Why are you opening it?

[Work]
[Research]
[Entertainment]
[I don't know]
```

---

# Morning Reflection Flow

The ideal day begins in Reflection Mode. This shifts the emotional tone of the app from:
- reactive intervention software

to:
- intentional daily formation software

Example morning flow:

```text
Good morning Shane

Today's focus:
- Purity
- Patience with family
- Discipline in work

Prayer Queue:
3 people remaining

Morning Reflection:
- What's on your mind?
- What are you worried about?
- What do you need from God today?

Today's Goals:
- Finish replay audit
- Exercise
- No aimless browsing

Encouragement:
"His mercies are new every morning." — Lamentations 3:23
```

This creates grounding, intentionality, awareness, mission alignment, and emotional honesty before distractions begin.

---

# Three System Modes

## 1. Reflection Mode
(Intentional / Morning / Deep interaction)

Used for:
- journaling
- prayer
- planning
- reports
- reflection
- goals
- reviewing trends
- AI insights

## 2. Intervention Mode
(Throughout the day)

Used for:
- hourly prompts
- Chrome intervention
- emotional check-ins
- prayer prompts
- temptation interruption
- awareness resets

## 3. Review Mode
(Evening / Weekly)

Used for:
- AI reports
- trend analysis
- relapse/victory review
- gratitude
- planning tomorrow
- evaluating patterns

---

# Journal System

## Journal Panel

The Reflection Mode landing page should contain a dedicated Journal Panel. The user should be able to:

- answer guided questions
- freely journal thoughts at any time
- review journal history
- search/filter entries

Structure:

```text
Journal Panel
-------------
Tabs or sections:

1. Guided Check-In
2. Free Journal
3. Journal History
```

---

# Guided Check-In Questions

Initial questions:

1. What's on your mind?
2. What are you worried about?
3. How does God feel about you right now?

These should:
- be savable
- be AI-analyzable
- feed into reports/categories/trends

The third question is especially valuable because it reveals perceived relationship-with-God state, which may predict emotional/spiritual condition more strongly than behavior itself.

---

# Journal Data Model

Both guided answers and free journaling share the same backend structure.

Guided check-in entry:

```json
{
  "entry_type": "guided_checkin",
  "responses": {
    "mind": "...",
    "worry": "...",
    "god_view": "..."
  },
  "free_text": null
}
```

Free journal entry:

```json
{
  "entry_type": "free_journal",
  "responses": {},
  "free_text": "Today I feel..."
}
```

---

# AI Categorization System

Journal/report AI can categorize entries into themes such as:

- Anxiety
- Loneliness
- Temptation
- Shame
- Hope
- Gratitude
- Exhaustion
- Career stress
- Financial pressure
- Relationship stress
- Spiritual discouragement
- Victory / encouragement
- Avoidance
- Purpose / calling

Example AI weekly report:

```text
Weekly Report
- Most common category: Anxiety
- Peak temptation windows: evenings after isolation
- Common worry theme: finances + trading pressure
- Most repeated belief: "God is disappointed in me"
- Positive trend: gratitude mentions increased 40%

Suggested interventions:
- contact friend after 9pm isolation
- reduce late-night screen time
- review scriptures on grace/identity
```

---

# PrayerMate System

## Concept

A PrayerMate-style system presents 5 random people per day, one at a time, with a quick "I prayed" action.

Popup example:

```text
🙏 Pray for: Sarah

[✓ I prayed for Sarah]
[Skip for now]
```

## Prayer Rotation Logic

Requirement: avoid repeating names until all active people have been prayed for, while still presenting them randomly.

Implementation:

```text
1. Start with all active people in an unprayed pool.
2. Randomly select from that pool.
3. When user confirms "I prayed":
   -> remove from pool
4. Continue until pool is empty.
5. Refill + reshuffle all active people.
```

Important: only remove from the pool after actual confirmation, not merely because they were shown.

## Prayer Data Model

```json
{
  "date": "2026-05-16",
  "daily_prayer_people": [
    {
      "person_id": "person_001",
      "name": "John Smith",
      "shown_at": "2026-05-16T09:15:00",
      "prayed": true,
      "prayed_at": "2026-05-16T09:16:30"
    }
  ]
}
```

## Potential Future Prayer Features

- prayer notes per person
- needs/categories
- prayer history
- reminders
- encouragement follow-ups

Example notes structure:

```text
Person notes:
- Needs prayer for job search
- Health concerns
- Family stress
- Encouragement
```

---

# Architectural Direction

Suggested top-level structure:

```text
PurityAppMainWindow
    -> Landing/dashboard shell (Reflection Mode)

InterventionPopupManager
    -> lightweight transient popup system (Intervention Mode)
```

Shared backend systems:
- event pipeline
- AI categorization
- reporting
- journal storage
- prayer state
- intervention state
- focus state
- risk scoring

---

# Core UX Principle

The popup/intervention system should NEVER feel:
- punitive
- guilt-driven
- noisy
- exhausting

Instead it should feel:
- caring
- grounding
- supportive
- gently interruptive
- companion-like

The landing page becoming the primary experience helps avoid the app becoming emotionally associated with failure or stress.

The app should primarily feel:
- encouraging
- intentional
- reflective
- grounding
- spiritually orienting

