# MAC-68 implementation plan

## User outcome

A contributor can run one command before opening a pull request and get the same backend,
frontend, schema-drift, migration, and whitespace checks that protect the repository in CI.

## Files touched

- `scripts/pre-pr.mjs`: orchestrate the complete local gate and stop on the first failure.
- `package.json`: expose the gate as `pnpm pre-pr`.
- `README.md`: list the command and explain its fresh-database cost.
- `CLAUDE.md`: require the Linear pickup and pre-PR steps in the canonical workflow.
- `AGENTS.md`: direct Codex to the existing repository instructions without duplicating them.

## Approach

Use a small Node script so the command works from the repository root without shell-specific
subshell syntax. It starts the existing Docker Postgres service idempotently, regenerates the API
client, runs the Python and Node CI checks, and finishes with `git diff --check`.

Hash the generated client before and after regeneration. This catches drift even when generated
files already have unrelated working-tree changes, which a plain `git diff --exit-code` cannot
distinguish locally.

Run pytest with `--create-db` to match CI's clean migration path. This is slower than the default
reused local test database, so the README calls out the tradeoff explicitly.

## Alternatives rejected

- A long inline `package.json` command is harder to read, diagnose, and run across shells.
- Calling only `pnpm test` misses Django because the API package is only a Turbo schema shim.
- Reusing the local pytest database is faster but does not prove migrations work from scratch.
- Duplicating all workflow rules in `AGENTS.md` would create two instruction sources that drift.

## Concepts in play

- Node's `spawnSync` preserves each tool's live output and exit status.
- A content digest detects generator side effects independently of Git staging state.
- Fail-fast sequencing keeps the first actionable error visible.
- An idempotent Docker Compose start avoids taking ownership of an already-running database.

## Blast radius

The command is opt-in and changes no runtime application behavior. It can start the local database
container and recreate the Django test database. It never stops containers or changes development
data.

## Deliberately unhandled

The command does not install dependencies, repair formatting, upload screenshots, push branches,
or open pull requests. Those actions remain explicit.

## Open questions

None. Alex explicitly requested a single pre-PR command and approved making the workflow durable.
