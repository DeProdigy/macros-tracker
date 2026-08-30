# MAC-40: targets endpoints, create, list, and the current singleton

Approved 30 Aug 2026. Linear:
[MAC-40](https://linear.app/hintology/issue/MAC-40/targets-endpoints-create-list-and-the-current-singleton).

## Slice and exception

**Slice 1 of 3**, which ends on: *a user can now set their own calorie, protein,
and fiber targets by hand and change them later.*

Three endpoints in one ticket rather than three slices, claiming the Gate 0
exception for the generated client: every API change costs a
`pnpm generate:api`, a committed diff, and a drift check. These three are one
read-write pair plus its singleton.

This is the ticket that makes MAC-38's table and MAC-39's clamp reachable.
Neither was callable from anything before it.

## Files

`serializers.py`, `views.py`, `urls.py` and `tests/test_endpoints.py` in
`apps/api/targets/`, one line in `config/urls.py`, one signature change in
`services.py`, and the regenerated client.

## The routes

```
POST /api/targets/           create a new TargetVersion         201
GET  /api/targets/           every version, newest first        200
GET  /api/targets/current/   the version in effect now          200 or 404
```

No `history/`. Targets are append-only, so the collection is the history. No
`PATCH` and no `PUT`: editing writes a new version through the same `POST`.

`current/` is routed above any future *untyped* or `<str:pk>/` detail route,
which would swallow the literal `current` as an id. An `<int:pk>/` route cannot,
because that converter matches digits only. Review caught the overstatement, and
the mutation below uses `<str:pk>/` for exactly that reason. Giving the detail
route `<int:pk>/` when it arrives removes the hazard entirely.

## The question MAC-53 left open, answered

`User.current_weight_lb` is optional, because doc 26 makes exiting onboarding
early a supported end state. So a user can reach Settings having answered
nothing, and the protein bound needs a weight.

**A missing weight skips the protein bound and keeps the other two.**

Refusing the write was the alternative, and it blocks the exact person slice 1
exists for: someone who skipped onboarding and is setting targets by hand,
which is their only route to having any. Refusing would make the skip a trap.

The cost is real and small. Calories and fiber take flat bounds and need no
weight, so both survive. Only protein's scales. A user with no stored weight can
set a nonsense protein target, which is a wrong number rather than a dangerous
one, and calories are the bound that matters for harm.

**The first version gated on sex *and* weight, and review caught that it was
wider than the argument above.** None of the three absolute bounds reads sex.
`absolute_protein_range` reads `weight_lb` and nothing else, so requiring a whole
`Profile` dropped the guard for a user who answered the weight question and
skipped the sex one, with the number it needed sitting right there.

`reject_outside_absolute` now takes `Decimal | None` rather than
`Profile | None`, and `absolute_protein_range` takes a weight too.
`clamp_to_suggested` keeps the full `Profile`, because the suggested calorie
floor genuinely does read sex.

Changing the signature once, here, was cheaper than changing it again when MAC-51
adds the second caller. It was already changing in this ticket.

## "Not in the future" cannot be checked exactly

`effective_from` comes from the client because the server cannot work out the
user's today. `User.timezone` is `"UTC"` for everyone until MAC-48, and doc 02
already has the client send its own `local_date` for `DailyLog` for that reason.

A device in UTC+14 is legitimately a day ahead of the server. Refusing that would
break the endpoint for New Zealand every afternoon.

So the guard allows one day of slack. That accepts every real timezone and still
refuses what it exists for: a date weeks out, which `current()` would return
before it applies. MAC-38's docstring names this ticket as where the rule lives.

## Two serializers, not one with `read_only_fields`

The read shape carries `source` and `ai_rationale`. A client that can write
`source` can lie about where a number came from, and MAC-44's history screen
labels rows `MANUAL` or `ONBOARDING AI` from it.

Sharing one class and marking fields read-only puts that hole one relaxed entry
away. `accounts/serializers.py` already makes this argument for `User`, and it
was right there too.

## Alternatives rejected

- **`ListCreateAPIView`.** Four fewer lines, and it hides which method does what
  behind a base class. `uploads` and `accounts` both use plain `APIView`, and
  `@extend_schema` has to be spelled out either way.
- **Taking `weight_lb` in the request body.** Works from onboarding, where the
  client has it. Fails from Settings, where nobody asked for a weight and the
  screen would invent a field to satisfy a server-side guard. MAC-53 removed the
  need entirely.
- **An empty 200 from `current/`.** Makes every caller null-check a body that
  claims to be a target. The resource genuinely does not exist.

## Blast radius

First endpoints in the epic, so `openapi.json` moves and the drift job has
something to check. Hooks generate as `useListTargets`, `useCreateTarget` and
`useGetCurrentTarget`, from explicit `operation_id`s.

One shipped signature changed: `reject_outside_absolute` now takes
`Decimal | None`, a weight, and `absolute_protein_range` with it. The only caller
is this ticket.

## Verification

Six mutations, each caught:

| Mutation | Result |
| ---------------------------------------------- | --------------------- |
| The future-date check is removed | 1 test fails |
| The absolute clamp is not applied on create | 3 tests fail |
| The date skew widens from 1 day to 30 | 1 test fails |
| `current/` is routed below a `<str:pk>/` route | 3 tests fail |
| A missing weight refuses instead of skipping | 2 tests fail |
| The protein gate requires sex as well as weight | 1 test fails |

Gates: ruff, ruff format, mypy on 57 files, 356 tests, prettier, `pnpm lint`,
`pnpm check-types`, `pnpm test`, client regenerated.

## A process change, since it caused three findings last round

On MAC-53, three of five review findings were comments I wrote in the same commit
that made them false. That is a pattern rather than three slips.

This ticket was written in a different order: code first, green, then the
comments against what the code actually does.

**It half worked.** The comments describe real behaviour this time, and review
still found two wrong: `<int:pk>` cannot collide with `current/`, and `User.sex`
is blank-with-default rather than nullable. Both were claims about code outside
the diff, which the new order does not help with.

It also created a failure the old order would not have. drf-spectacular puts view
docstrings into the OpenAPI description, so writing them after `pnpm generate:api`
made the committed client stale and the drift job caught it. The comments here
are part of the API contract, so "comments last" has to mean "regenerate last"
too.

## Deliberately unhandled

- **`POST /api/targets/proposals/`.** MAC-51, slice 2.
- **Pagination on the list.** A user will have a handful of versions. Adding it
  now would change the response shape for nobody's benefit.
- **Anything about onboarding as a flow.**

## Open questions

- **Should a version be deletable?** No route offers it, and append-only argues
  against. MAC-38's admin allows it for support. Nothing has asked for an API
  route, so none exists.
