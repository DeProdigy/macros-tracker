# 02 — Data Model

## The central decision: the day is an entity

Every requirement in this app orbits "what day was this?" — daily totals, streaks, history navigation, which targets applied. The naive approach stores a timestamp on each entry and computes the day at read time. That breaks in specific, annoying ways: timezone math on every query, no clean index, and travel retroactively rewrites history.

Instead, `DailyLog` **is a real row**. Entries belong to a day by foreign key.

```
DailyLog
  id
  user            FK → User
  date            DateField          # the user's local calendar date
  target_version  FK → TargetVersion # targets active on this day
  created_at
  UNIQUE (user, date)

FoodEntry
  id
  daily_log       FK → DailyLog
  eaten_at        DateTimeField      # UTC, for ordering within the day
  photo_key       CharField          # R2 object key
  description     TextField          # what the user typed
  calories        IntegerField
  protein_g       DecimalField
  fiber_g         DecimalField
  ai_raw_response JSONField          # what the model returned, before user edits
  was_edited      BooleanField       # did the user override the estimate
  created_at
  updated_at
```

**No** `local_date` **column on** `FoodEntry`**.** Day membership is the FK, not a denormalized copy. `created_at`, `updated_at`, `eaten_at` are all plain UTC — normal Django practice, no special handling.

### What this design gives you for free

| Requirement | How it falls out |
| -- | -- |
| Group entries by day | Indexed FK join. No timezone math at read time |
| "Log this to yesterday" | Point the entry at yesterday's `DailyLog`. No override flag needed |
| Streaks | Consecutive `date` values in `DailyLog`. One query |
| Historical target accuracy | `DailyLog.target_version` was resolved when the day was created |
| History navigation | Paginate `DailyLog` by date descending |

### Write path

1. Client sends `local_date` (its own calendar date) plus the entry payload
2. Server does `get_or_create(user=..., date=local_date)`
3. On create, resolve the user's current `TargetVersion` and attach it
4. Create the `FoodEntry` pointed at that `DailyLog`

`DailyLog` rows are created lazily on first log, so there are no empty rows for days the user skipped — which is also exactly what makes the streak query correct.

### Known edge cases

* **Traveling across timezones:** the device's local date at the moment of logging wins. Dinner at 9pm in Barcelona lands on that Barcelona date and stays there forever. This is the desired behavior.
* **Logging at 11:59pm then changing timezone:** can produce a mildly surprising day assignment. Accepted; the "log to previous day" affordance covers it.
* **User's timezone** is stored on the profile and refreshed on app launch, used for server-side defaults when the client doesn't supply a date.

## Targets

```
TargetVersion
  id
  user             FK → User
  calories         IntegerField
  protein_g        IntegerField
  fiber_g          IntegerField
  source           CharField     # "onboarding_ai" | "manual"
  ai_rationale     TextField     # explanation shown to the user, nullable
  effective_from   DateField
  created_at
```

**Append-only. Never updated in place.** Adjusting targets writes a new row.

* Current targets = latest `TargetVersion` for the user by `created_at`
* A `DailyLog` captures its `target_version` FK at creation, so past days are evaluated against what was true then
* Changing targets today does not retroactively rewrite last week's progress

This is the standard slowly-changing-dimension pattern. Worth internalizing — it shows up constantly in real systems, and "why did last month's numbers change?" is a bug class it eliminates entirely.

## Accounts

```
User (custom, AbstractBaseUser)
  id
  email                  unique, used as username
  is_email_verified      BooleanField
  apple_user_id          CharField, nullable, unique  # Sign in with Apple subject
  timezone               CharField                     # IANA name, e.g. "America/New_York"
  onboarding_completed   BooleanField
  ai_calls_this_month    IntegerField                  # quota counter
  created_at
  deleted_at             DateTimeField, nullable       # soft delete
```

**Custom user model from the very first migration.** Swapping Django's user model after tables exist is genuinely painful. This is non-negotiable and belongs in the first backend ticket.

Email as the identifier, no separate username field.

## Derived, not stored

Daily totals (`sum(calories)`, `sum(protein_g)`, `sum(fiber_g)`) are **computed on read** via aggregation, not stored on `DailyLog`.

Reasoning: a stored total is a cache, and a cache that can disagree with its source is a bug waiting to happen — every edit and delete has to remember to update it. At this data volume the aggregate query is trivially fast. If it ever isn't, denormalize then, with measurements in hand.

Same for streak length: computed from `DailyLog` rows, not stored.

## Migration sequencing

Order matters, because of the FKs:

1. `accounts` — custom User (must be first, before any migration references AUTH_USER_MODEL)
2. `targets` — TargetVersion
3. `logging` — DailyLog (FKs User + TargetVersion), then FoodEntry (FK DailyLog)

## Indexes

* `DailyLog (user, date)` — unique, and covers the primary lookup
* `DailyLog (user, date DESC)` — history pagination and streak scanning
* `FoodEntry (daily_log, eaten_at)` — ordering entries within a day
