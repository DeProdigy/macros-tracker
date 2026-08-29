# MAC-38 — Targets app foundations: the TargetVersion model

Approved 29 Aug 2026. Linear:
[MAC-38](https://linear.app/hintology/issue/MAC-38/targets-app-foundations-the-targetversion-model).

First ticket of E3. One model, no endpoints, no AI, no UI.

## Context

`apps/api/targets/` was an empty directory. This makes it a Django app and lands
the model everything else in the epic hangs off: MAC-39's clamp produces values
for it, MAC-40's endpoints read and write it, MAC-44's history screen renders it.

## Files

| File                                            | Change                                       |
| ----------------------------------------------- | -------------------------------------------- |
| `apps/api/targets/{__init__,apps}.py`           | New app                                      |
| `apps/api/targets/models.py`                    | `TargetVersion` and its queryset             |
| `apps/api/targets/admin.py`                     | Read-only registration                       |
| `apps/api/targets/migrations/0001_initial.py`   | Generated                                    |
| `apps/api/targets/tests/test_models.py`         | 10 tests                                     |
| `apps/api/config/settings/base.py`              | `INSTALLED_APPS`                             |
| `apps/api/pyproject.toml`                       | mypy's `files` list                          |

That last one is the quiet one. `[tool.mypy] files` is an explicit list of four
entries, not a glob. A new app left out of it is never type-checked, and CI stays
green while checking nothing.

## Three decisions

### `effective_from` has no default, deliberately

The ticket asked what this field is for, since doc 02 names it once and never
again. The obvious implementation is `default=timezone.now().date()`, and it is
wrong here.

`User.timezone` is `"UTC"` for every user, because the client never sends one
(MAC-48). A server-side "today" is therefore UTC's today, and a caller in Los
Angeles saving at 5pm gets tomorrow's date.

Doc 02 already solved this. Its write path has the client send its own
`local_date` and the server trusts it. `effective_from` follows the same path,
set by MAC-40's endpoint from a client-supplied date.

The general shape: **a server-side "today" is a timezone assumption wearing a
default's clothing.** Putting one in a column hides the assumption where nobody
reviewing the endpoint will see it.

### `ordering = ("-created_at", "-id")`

"Current targets are the latest by `created_at`" is ambiguous the moment two rows
share a timestamp. Without a tiebreak the database may return either, so
`current()` could flip between two different calorie targets across identical
requests. The `-id` makes the ordering total.

Worth recording how the test for this went wrong first. The original version
created two rows inside one transaction and asserted determinism, on the
assumption that `auto_now_add` would collide. It does not: `auto_now_add` reads
Python's clock per row, so ordinary saves land microseconds apart. Removing
`-id` left all ten tests green.

The rewritten test forces the collision with a `.update()` on `created_at`,
which is what `bulk_create`, a data migration, or a fixture would produce. It now
fails without the tiebreak.

The lesson generalises: **an untested tiebreak is one a future reader deletes as
noise**, and a test that cannot produce the condition it names is worse than no
test, because it looks like coverage.

### One composite index on `(user, -created_at)`

The FK indexes `user` alone, which still leaves a sort. This query runs whenever
a user logs food on a new day, and adding an index later needs a migration
anyway. Doc 02's index section does not list it; that is a Linear edit still
outstanding.

## Alternatives rejected

- **An `is_current` boolean.** A second source of truth that can disagree with
  the ordering, and keeping it accurate means writing to the previous row on
  every change. That is the in-place update the append-only model exists to
  avoid, reintroduced as an optimisation.
- **`Meta.get_latest_by` plus `.latest()`.** Reads well, but raises
  `DoesNotExist` when the user has no targets. That is a supported state (doc 26
  makes skipping onboarding a real exit), not an exception, and wrapping every
  call site in a `try` is worse than returning `None`.
- **An `effective_to` column.** Would make the history screen's date range a
  direct read rather than a computation over adjacent rows. Rejected because
  every save would write to the previous row. The in-place update again, wearing
  a different hat.
- **A nullable `ai_rationale`.** Two ways to spell "empty", and every reader has
  to handle both. `blank=True` with `""` is the one place Django's own docs are
  unambiguous.

## The admin is read-only

Editing a version in place contradicts the model: a `DailyLog` already points at
the row, so changing its numbers silently rewrites history for every day that
referenced it. The admin is exactly where someone does that by accident while
trying to help a user.

Adding is blocked too. A hand-made row skips MAC-39's clamp and MAC-47's
`onboarding_completed` write, so it would be a target set no code path can
produce.

Deleting stays available. Support occasionally needs to undo a bad row, and
unlike an edit it is visible: the version disappears rather than quietly holding
different numbers.

## Blast radius

Almost none. New app, new table, and nothing imports it yet. No endpoints means
`openapi.json` does not move, so the `api-client-drift` job has nothing to say.

## Verification

Three mutations, each caught:

| Mutation                         | Result                                        |
| -------------------------------- | --------------------------------------------- |
| Drop `-id` from the ordering     | The collision test fails                      |
| `current()` returns `.last()`    | Two tests fail                                |
| `for_user` drops its filter      | The cross-user isolation test fails           |

Gates: ruff, ruff format, mypy on 49 files, 265 tests, `makemigrations --check`
clean, prettier clean.

## Deliberately unhandled

- **The `DailyLog` backfill.** MAC-45, and it needs E4's `DailyLog` to exist.
  Not stubbed.
- **Setting `onboarding_completed`.** MAC-47.
- **Endpoints** (MAC-40), **the clamp** (MAC-39), **the `AICall` table** (MAC-49).

## Open questions

- Doc 02's index section should gain the `TargetVersion (user, created_at)` line.
  A Linear edit, not a repo one, and not done here.
- Whether `effective_from` should ever differ from the save date, which is what
  a client-supplied value makes possible. No screen offers a future start date,
  so MAC-40 should validate that it is not in the future rather than leaving the
  question open.
