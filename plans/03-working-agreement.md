# 03 — Working Agreement & AI Workflow

## Why this document exists

The toolchain below can build this app almost without the author. That is precisely the risk. The stated goal is levelling up React Native and Django — an app that ships without teaching anything is a failed project by this project's own definition.

So: adopt the full workflow, and apply deliberate discipline about *which* tickets get automated.

## Ticket labels that govern usage

Every ticket carries one of:

* `you-implement` — the author writes the code. Claude explains, reviews, unblocks, answers questions. Covers: Django models, DRF serializers and views, RN screens, navigation, state management, the AI integration, anything with a real design decision inside it.
* `auto-ok` — hand to `make-it-so` in auto mode, no guilt. Covers: scaffolding, config, CI YAML, lint setup, boilerplate, dependency wiring, generated-code plumbing.

The rule is decided at planning time, not at 11pm when auto mode looks tempting. That's the entire point of writing it down.

## Skills in use

Installed under `.claude/skills/`:

| Skill | Purpose |
| -- | -- |
| `grill-me-with-docs` | Interrogate an idea before building. Produces plan docs. Used at project and feature kickoff |
| `make-it-so` | Fetch ticket, mark in progress, codebase dive, read ACs, ask questions, produce a plan, then implement, commit, and open a PR |
| `oh-behave` | Read PR review comments, propose implementing or pushing back, resolve the thread |
| `code-review` | Review pass before requesting human review |

Plus **Plannotator** ([plannotator.ai](http://plannotator.ai)) for viewing and annotating plans in the browser before approving them.

Sources: `mattpocock/skills` for `grill-me-with-docs`. The rest came from Jason (staff engineer) as zips — install into `.claude/skills/`.

## The loop, per ticket

1. **Pick a ticket** from the current milestone in Linear
2. `make-it-so` — fetches details, marks in progress, dives the codebase, asks clarifying questions, produces a plan
3. **Review the plan in Plannotator.** Annotate it. Refine it. This is where the leverage is — a good plan makes the implementation boring
4. **Then it forks:**
   * `auto-ok` → approve the plan, let it run to completion
   * `you-implement` → the plan becomes the author's own guide. Write the code by hand. Ask Claude questions freely; do not ask it to write the file
5. **PR opened**, `code-review` pass runs first
6. **Human review on GitHub.** Leave real comments — this is deliberate practice at the thing an EM does daily
7. `oh-behave` processes the comments, implements or argues back
8. **Merge.** Railway auto-deploys. Close the ticket

## CLAUDE.md

Repo root, committed. Contains at minimum:

```
This is a learning project. The owner is levelling up React Native and Django.

For tickets labeled `you-implement`:
- Do NOT write implementation code unless explicitly asked
- Explain concepts, review code, ask guiding questions, unblock errors
- If asked "how do I do X", answer with the concept and a pointer, not a finished file

For tickets labeled `auto-ok`:
- Implement freely

Always:
- Regenerate packages/api-client after any API change
- Explicit DRF serializers, never fields = "__all__"
- Business logic in services.py, thin views
- TypeScript strict; no `any` without a comment justifying it
```

## Plans folder

These Linear documents are the source of truth for planning. Mirror them into `plans/` in the repo so Claude Code has them in context:

```
plans/
├── 00-app-overview.md
├── 01-architecture.md
├── 02-data-model.md
├── 03-working-agreement.md
└── features/
    └── <one per feature area>
```

When starting a feature, feed the relevant plan doc into the session rather than re-explaining decisions.

## Ticket format

Every ticket, without exception:

* **Context** — why this exists, link to the plan doc
* **What you're learning** — the concept this ticket teaches. If a ticket teaches nothing, question whether it should be `auto-ok`
* **Acceptance criteria** — checkable, specific
* **Implementation guidance** — enough detail to pick up cold weeks later
* **Label** — `you-implement` or `auto-ok`, plus area labels

## Spike tickets

Not everything ships code. Periodic `spike` tickets — read the docs on X, write five bullets on what you learned — cement concepts and mirror how real teams handle unknowns. They also make good interview material.

## Decisions log

Architectural decisions and their reasoning get appended to this project's docs as they're made. Not ceremony: "here's a project where I made and documented real tradeoffs" is directly useful material for Senior EM / Director interviews.
