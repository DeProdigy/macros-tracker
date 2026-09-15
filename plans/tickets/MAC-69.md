# MAC-69: Fix Railway API build with required OpenAI setting

## Problem

Railway cannot build the API image. The Docker build runs Django `collectstatic` with production settings. Production settings require `OPENAI_API_KEY`, but the build command does not provide it.

## Files Touched

- `apps/api/Dockerfile`
- `plans/tickets/MAC-69.md`

## Approach

Add a fake `OPENAI_API_KEY` only to the `collectstatic` `RUN` command. Keep the real key in Railway for the running service. Update the Dockerfile explanation so it lists every required production setting used during the build.

## Alternatives Rejected

- Do not declare the real key as a Docker `ARG`. The static collection step does not call OpenAI. A real secret does not belong in Docker build inputs.
- Do not make `OPENAI_API_KEY` optional in production settings. A missing runtime key must continue to stop the service at startup.
- Do not remove `collectstatic` from the image build. Build-time static validation prevents a later runtime failure.

## Concepts

Docker command-scoped environment variables exist only for one `RUN` step. Django imports all selected settings before it runs a management command. Railway service variables remain the runtime source of the real key.

## Blast Radius

The change affects only the API image build. It does not change API behavior, database state, mobile code, or the generated client.

## Deliberately Unhandled

This change does not rotate or inspect the real OpenAI key. It does not change AI request behavior.

## Open Questions

None. Alex approved the build-only placeholder approach.
