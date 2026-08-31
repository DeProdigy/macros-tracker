# Design artifacts

This directory holds durable visual references for Macros Tracker.

The canonical rules and screen inventory live in
[`plans/canonical-mvp-visual-design-and-approved-screens.md`](../plans/canonical-mvp-visual-design-and-approved-screens.md).
That document defines how to review and approve an artifact.

## Authority

- The canonical experience document defines behavior and navigation.
- An approved artifact in `exports/mvp/` defines presentation for its named screen and state.
- A screenshot cannot introduce behavior that the canonical experience does not specify.
- Files under `plans/archive/` are history and must not supply replacement designs.

## Layout

| Path           | Contents                                                                  |
| -------------- | ------------------------------------------------------------------------- |
| `source/`      | Editable source files, including original `.dc.html` files when available |
| `exports/mvp/` | Approved PNG exports used by implementation issues                        |

## Artifact index

Add one row when an artifact arrives. Do not mark it Approved until Alex reviews it against the canonical screen inventory.

| Artifact            | Screen and state | Original source | Status | Approved by | Notes |
| ------------------- | ---------------- | --------------- | ------ | ----------- | ----- |
| _None gathered yet_ |                  |                 |        |             |       |

Use Candidate, Approved, or Superseded for Status.
