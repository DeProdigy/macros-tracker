# MAC-60 implementation plan

## User outcome

A user can open a past empty day, understand that it is empty, and backfill food onto it.

## What already existed

MAC-55 and MAC-59 delivered most of this ticket's scope. The calendar sheet, both day endpoints,
the `date` route parameter, and the future-date clamp were all already in place. This plan covers
the remainder.

## Files touched

- `apps/api/accounts/serializers.py`: add the read-only `has_logged_food` field to `UserSerializer`.
- `apps/api/accounts/tests/test_current_user.py`: cover the flag, including ownership.
- `apps/mobile/app/(app)/today.tsx`: pick one of three empty-day states, and name the day in the
  main action.
- `apps/mobile/lib/session.tsx`: add `markFoodLogged`, which records the first log in the cached
  user.
- `apps/mobile/app/(app)/log-food.tsx`, `apps/mobile/app/(app)/photo.tsx`: call it after a save.
- `apps/mobile/jest.global-setup.js`: pin the test timezone.
- `apps/mobile/package.json`: register that global setup.
- `apps/mobile/__tests__/today.test.tsx`: cover the three empty states.
- `apps/mobile/__tests__/local-day-dst.test.ts`: cover both daylight-saving transitions.
- `apps/mobile/__tests__/day-picker.test.tsx`: cover the calendar sheet.
- `apps/mobile/__tests__/session.test.tsx`: cover `markFoodLogged`.
- `apps/mobile/__tests__/log-food.test.tsx`, `apps/mobile/__tests__/photo.test.tsx`: assert the
  screens record the first log.
- `packages/api-client/`: regenerated.

## Approach

### Telling a first run apart from an empty day

The app could not tell "never logged anything" from "nothing logged yet today". Both arrive as a
day with no entries. The canonical flow doc asks for different copy in each case.

`UserSerializer` gains `has_logged_food`, a `SerializerMethodField` running one `EXISTS` query. It
uses the `user.daily_logs` reverse accessor, so `accounts` does not import `entries`. It spans the
join to `entries`, so a `DailyLog` left behind by a rolled-back save reads as empty.

The session fetches the user once at launch and keeps it in React state. So a save that flips the
flag on the server would not reach the app until the next launch. `markFoodLogged` writes it
locally instead of refetching. The flag only ever moves false to true, so a local write cannot
disagree with the server in the direction that matters.

### Three empty states

`emptyDayCopy(isToday, hasLoggedFood)` is a pure function returning a title and an optional body.

| Case | Title | Body |
| -- | -- | -- |
| First run | Nothing logged yet | Point the camera at your food. The app fills in the numbers. |
| Empty today | Nothing logged yet | none |
| Past empty | Nothing logged this day | You can still add food to this day. |

The main action reads `LOG FOOD` on today and `ADD TO THIS DAY` on a past day. `photo.tsx` already
said `SAVE TO THIS DAY`, so the two now agree.

### The timezone pin

Every helper in `lib/local-day.ts` reads the ambient timezone. The suite inherited the machine's
zone, so it tested one thing on a laptop in New York and another on a CI runner in UTC. UTC never
shifts its clocks, which is the worst case: a daylight-saving bug passes CI and appears only on a
phone.

`jest.global-setup.js` pins the run to America/New_York. Jest ignores `process.env.TZ` set inside a
test file, because the runtime has cached the zone by then. Global setup works because Jest forks
its workers afterwards.

## Alternatives rejected

- **Call `GET /api/foods/` from Today to detect a first run.** An empty food library does mean the
  user never logged. It also fires on every empty morning and returns up to 100 rows.
- **Put the flag on the day resource.** A day is one date. "Has this person ever logged" is a fact
  about the person.
- **Refetch `/api/users/me/` after a save.** A whole round trip to flip one boolean the client can
  already deduce.
- **Drop the first-run state and rely on `first-food.tsx`.** That screen appears once, right after
  onboarding. A user who quits and returns never sees it again.
- **Set `process.env.TZ` inside the test file.** It does nothing under Jest. A probe proved it, and
  the tests had been passing only because the machine was already in New York.

## Django and React Native concepts

**`SerializerMethodField`.** It adds a computed field DRF cannot read off a column. It runs once per
object serialized. That is safe here, because only one user is ever serialized. In a list endpoint
it becomes one query per row, which is the classic N+1.

**Reverse accessors and app dependency direction.** `user.daily_logs` works without importing
`entries`. Import direction is a design choice. `entries` already depends on `accounts`, and
reversing that would leave neither app importable alone.

**Derived state over stored state.** The empty-state choice is computed during render from two
booleans. An effect would paint the wrong copy for one frame and then correct itself, which reads
as a flicker.

**Caching a server fact in client state.** This is safe only because the flag is monotonic. It
moves false to true and never back. The same pattern applied to a field that can move both ways
hides a real server change behind a stale local one.

## Blast radius

- The generated `User` type gains a required field. Every fixture typed as `User` must carry it.
- `pnpm generate:api` output lands in the same commit. CI fails on drift otherwise.
- The timezone pin changes the zone every existing mobile test runs in. All 239 pass.
- No migration. No model change.

## Deliberately unhandled

- A timezone that shifts its clocks at 00:00, such as America/Santiago, where the midnight the
  helper starts from does not exist. Jest holds one zone per run, so covering it needs a second Jest
  project. Not worth it for one user in one American zone.
- The twelve-week grid, streaks, weekly summaries, and offline backfill. Out of scope in the ticket.
- The "What should I eat?" card in the design candidates. That is the advice feature, which the MVP
  does not include.
- Midnight rollover while the app sits open on Today.

## Design authority

`design/exports/mvp/` holds no approved artifact. Candidates 16, 17, and 18 informed the copy and
the layout. The canonical flow doc defines the behavior.

## Open question, answered

A past empty day shows the calorie ring at full budget, against the target that was in force on
that date. Alex confirmed this is correct.
