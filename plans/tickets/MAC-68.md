# MAC-68 implementation plan

## User outcome

A contributor can run one command before opening a pull request and get the complete backend,
frontend, schema-drift, migration, and whitespace checks required by the repository workflow.

## Files touched

- `scripts/pre-pr.mjs`: orchestrate the complete local gate and stop on the first failure.
- `package.json`: expose the gate as `pnpm pre-pr`.
- `README.md`: list the command and summarize the checks it runs.
- `CLAUDE.md`: require the Linear pickup and pre-PR steps in the canonical workflow.
- `AGENTS.md`: direct Codex to the existing repository instructions without duplicating them.

## Approach

Use a small Node script so the command works from the repository root without shell-specific
subshell syntax. It starts the existing Docker Postgres service idempotently and waits for its
healthcheck, regenerates the API client, runs the Python and Node checks, and finishes by checking
the branch diff from `origin/main` for whitespace errors.

Use the same generated-client diff sequence as CI: regenerate, add intent-to-add entries for new
files, and run `git diff --exit-code -- packages/api-client`. Generated files already staged for the
next commit remain valid, while regenerated unstaged drift fails the gate.

Run pytest with `--create-db` to match CI's clean migration path. This is slower than the default
reused local test database, so the script explains the reason next to the flag.

## Alternatives rejected

- A long inline `package.json` command is harder to read, diagnose, and run across shells.
- Calling only `pnpm test` misses Django because the API package is only a Turbo schema shim.
- Reusing the local pytest database is faster but does not prove migrations work from scratch.
- Duplicating all workflow rules in `AGENTS.md` would create two instruction sources that drift.

## Concepts in play

- Node's `spawnSync` preserves each tool's live output and exit status.
- Git's working-tree diff detects regenerated client changes against the staged baseline.
- Fail-fast sequencing keeps the first actionable error visible.
- Docker Compose waits for the existing database healthcheck before later commands use it.

## Blast radius

The command is opt-in and changes no runtime application behavior. It can start the local database
container, add intent-to-add index entries for new generated files, and recreate the Django test
database. It never stops containers or changes development data.

## Deliberately unhandled

The command does not install dependencies, repair formatting, upload screenshots, push branches,
or open pull requests. Those actions remain explicit.

## Open questions

None. Alex explicitly requested a single pre-PR command and approved making the workflow durable.
