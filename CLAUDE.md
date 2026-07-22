# CLAUDE.md

Planning source of truth lives in [`plans/`](./plans) — mirrors of the Linear
project docs. Feed the relevant plan doc into a session rather than
re-explaining decisions. Architecture is in
[`plans/01-architecture.md`](./plans/01-architecture.md); the working agreement
this file enforces is in
[`plans/03-working-agreement.md`](./plans/03-working-agreement.md).

---

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
