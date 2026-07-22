# 07 — Feature: Dashboard & Streaks

## Home screen

The screen the user opens several times a day. Everything else is secondary.

Shows, in priority order:

1. **Progress toward today's three targets** — calories, protein, fiber
2. **Remaining budget** in each, since that's the actionable number
3. **Streak count**
4. **Today's entries**, most recent first, with photo thumbnails
5. **Log food** — the primary action, always reachable

## The graph

Requirement: a good visual of daily limit vs. usage.

Recommended: three horizontal progress bars, one per macro, each showing consumed against target with a clear over-target state. Simple, scannable in half a second, works at any screen size.

**Important nuance in how "over" reads:** for calories, over target is a warning. For protein and fiber, over target is *good* — the goal is a floor, not a ceiling. Color and copy must reflect that, or the app will scold the user for hitting their protein goal. This is exactly the kind of domain detail that separates a real tool from a generic tracker.

Library options: `victory-native` or `react-native-svg` directly. For three bars, hand-rolled SVG is likely simpler than a charting dependency — but a weekly trend view later would justify one.

## Day navigation

Requirement: a good way to distinguish one day from another.

Recommended: a horizontally scrolling date strip pinned near the top — roughly a week visible, today highlighted, tap to jump. Swipe left/right on the main content to move a day at a time. Days with logs get a subtle marker so gaps are visible at a glance.

This is a meaningful RN exercise: horizontal `FlatList` with correct initial scroll position, gesture handling, and prefetching adjacent days with React Query so navigation feels instant.

## Endpoints

```
GET /api/days/today/           entries, totals, targets, remaining
GET /api/days/{date}/          same shape, any date
GET /api/days/                 paginated list for the date strip
GET /api/streak/               current streak, longest streak
```

Totals are computed via aggregation, not stored. See the data model doc.

Each day response includes the targets **that applied on that day**, from the `DailyLog`'s `target_version` — not today's targets. A day in the past must render against the goals that were real at the time.

## Streaks

**Definition:** consecutive days with at least one logged entry. Consistency, not achievement — the Whoop model. Missing a protein target does not break a streak; not logging does.

Computation: pull `DailyLog` dates for the user, descending, walk backward from today counting consecutive dates. Stop at the first gap.

Edge cases to decide explicitly:

* **Does today count before you've logged?** Recommended: the streak holds through today until the day ends. Showing a broken streak at 7am because breakfast isn't logged yet is demoralizing and wrong
* **Timezone:** "today" is the user's local date, from their stored timezone
* **Deleting the last entry of a day** removes that day from the streak. Decide whether the `DailyLog` row should be deleted when its last entry goes — this directly determines the answer

Display: current streak prominently. Longest streak is a nice secondary stat and nearly free once the query exists.

**Performance note:** walking every `DailyLog` row is fine at hundreds of days and wrong at scale. It's the right call now. Worth understanding *why* it's the right call — premature optimization here would cost real time for no user benefit.

## Empty states

Frequently skipped, always noticed:

* **No entries today** — invite to log, not a blank screen
* **No entries ever** — brief orientation to the core loop
* **A past day with no logs** — plainly stated, no error styling

## What you're learning here

* `FlatList` performance, `getItemLayout`, and initial scroll positioning
* Gesture handling and swipe navigation
* React Query prefetching and cache keys for date-addressed data
* Rendering data visualizations in RN without over-reaching for a library
* Aggregation queries in Django ORM
* Streak logic — deceptively fiddly, and a genuinely good algorithm exercise
