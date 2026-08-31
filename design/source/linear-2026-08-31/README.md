# Linear design intake — 2026-08-31

These 46 PNGs were downloaded from the Linear document
`CANONICAL — MVP Visual Design and Approved Screens` on 2026-08-31. The
filenames preserve the manifest Alex attached to that document.

They are source candidates, not implementation authority. Only files copied to
`design/exports/mvp/` after Alex's approval are approved designs.

## MVP review

| Files                                                          | Intake status                | Reason                                                                                                                                                         |
| -------------------------------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `01`, `02`, `05`–`10`, `12`–`15`, `18`, `21`, `22`, `36`, `38` | Candidate                    | Direction fits the canonical MVP; final approval and state coverage are still needed.                                                                          |
| `03`, `11`, `16`, `17`, `19`, `20`, `23`, `34`, `37`, `39`     | Candidate — revise           | Contains stale sequence, technical metadata, Advice, streak, auth, Health, quota, offline, or deletion copy that must be removed or separated before approval. |
| `04`, `40`                                                     | Superseded                   | Logs a meal before mandatory questions and targets and includes a skip path.                                                                                   |
| `24`–`33`, `35`, `44`                                          | Superseded for MVP           | Advice, Recap, History analytics, and day-close coaching are follow-up references.                                                                             |
| `41`–`43`, `45`, `46`                                          | Superseded as whole diagrams | Mixes useful MVP screens with superseded behavior. Individual current screens remain covered by their numbered source files.                                   |

## Important conflicts

- Mandatory first run is Welcome → Apple → verification → six questions →
  target result or adjustment → first-food prompt. No skip action.
- Today has no streak, Advice, Recap, or analytics History in MVP.
- Settings has no password auth, Health integration, notifications, or
  public-product controls in MVP.
- Offline queues are follow-up scope.
- Quota copy must use the canonical rolling-window policy, not daily or calendar
  month reset language.
- User-facing analysis screens must not expose compression sizes, R2 transfer
  details, or timing promises.

## Source manifest

The numbered files follow the manifest attached in Linear: screens `01`–`39`
and flow diagrams `40`–`46`. The original attachment remains in Linear for
provenance.
