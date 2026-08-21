# MAC-36 — Throttle is bypassable behind Railway's proxy: NUM_PROXIES is unset

Approved 21 Aug 2026. Linear:
[MAC-36](https://linear.app/hintology/issue/MAC-36/throttle-is-bypassable-behind-railways-proxy-num-proxies-is-unset).

## Context

MAC-27 shipped `POST /api/auth/sessions/` with a burst and a sustained throttle,
and MAC-28 added one to the refresh endpoint. All three are correct code. All
three are bypassable in production, and none of the 30 tests covering them can
see it.

DRF decides who a request came from in `BaseThrottle.get_ident`. With
`NUM_PROXIES` unset it falls through to its last line and uses the **entire**
`X-Forwarded-For` chain as the throttle identity. Railway always sends that
header and the client controls its left-hand end, so a different forged value
per request means a different cache key per request and a counter that never
climbs.

Locally there is no proxy, no header, and `get_ident` returns `REMOTE_ADDR`.
The bug exists only where it matters, which is why the tests are green.

The general form is worth naming, because it will come back: **a control keyed
on client identity is only as trustworthy as the proxy configuration under it.**
`SECURE_PROXY_SSL_HEADER` in `production.py` already draws exactly this trust
boundary for the HTTPS decision. This ticket draws it for a second header.

## Why this is not one line

Both directions of a wrong `NUM_PROXIES` are bad, and they are not equally
visible:

- Too low, or still unset, and the identity stays forgeable. The bug survives,
  silently.
- Too high and `addrs[-min(n, len(addrs))]` reaches past the real client into a
  proxy address. Every caller then shares a small pool of buckets, and ten
  sign-ins a minute across the whole world locks everyone else out.

The second is worse and would look like an outage, not a bug. Platforms also
disagree about whether the true client sits at the left or the right of the
chain. So the number gets measured from a real deployed request rather than read
off a documentation page.

## Approach: measure first, then fix

Two PRs, deliberately.

**PR 1 — measure.** Gunicorn's default access log format shows `%(h)s`, which is
`REMOTE_ADDR`, which behind Railway is always the proxy. Confirmed by probing
the deployed `/api/ping/`: it logged `100.64.0.3`, a carrier-grade NAT address
on Railway's internal network, and the forwarded chain appeared nowhere. So the
log format gains `%({x-forwarded-for}i)s` temporarily. No behaviour changes.

Then probe the deployed endpoint with a known, obviously fake left-hand entry
and read the chain back with `railway logs`. Three possible answers, and they
lead to different fixes:

| Logged chain               | Meaning                    | Fix              |
| -------------------------- | -------------------------- | ---------------- |
| `<forged>, <real client>`  | Railway appends. One hop.  | `NUM_PROXIES=1`  |
| `<real client>`            | Railway replaces the header | `NUM_PROXIES=1` |
| `<forged>` alone           | Railway passes it through  | Escalate — no value of `NUM_PROXIES` helps |

**PR 2 — fix.** Set the measured value, add the test, remove the temporary log
format, update doc 09.

Two deploys for a one-line setting is slower than guessing. Guessing upward
produces a global lockout on the endpoint every client must reach, so the extra
deploy is cheap by comparison.

## Files

| File                                       | Change                                                                |
| ------------------------------------------ | --------------------------------------------------------------------- |
| `apps/api/Dockerfile`                      | PR 1: `--access-logformat` with the forwarded chain. Reverted in PR 2  |
| `apps/api/config/settings/base.py`         | PR 2: `NUM_PROXIES` in `REST_FRAMEWORK`, commented with both failure directions |
| `apps/api/accounts/tests/test_sessions.py` | PR 2: a forged `X-Forwarded-For` does not earn a fresh bucket          |
| `plans/09-deployment-and-production-ops.md` | PR 2: the value is tied to Railway's topology and is rechecked if the platform or a CDN changes |

## `base.py`, not `production.py`

The ticket proposed `production.py`. This plan puts it in `base.py`, and the
reason is the bug itself: the hole existed because a production-only setting was
never exercised by a test. Keeping it production-only means the test has to fake
the value with `override_settings`, so the tested value and the deployed value
can drift apart again. Same shape, second time.

In `base.py` it is inert everywhere else. Local and CI requests carry no
`X-Forwarded-For`, so `get_ident` returns `REMOTE_ADDR` exactly as it does today.
The test then forges a chain and proves the real deployed value ignores it.

## The test, and how it could pass while proving nothing

A real proxy **appends** what it observed to whatever the client sent. Production
therefore sees `X-Forwarded-For: <anything the caller typed>, <address Railway
saw>`. A test that sends a bare forged header and asserts the bucket changed is
testing a request shape that cannot occur.

So the test sends two requests with different forged left-hand entries and the
same trailing address, and asserts both land in one bucket. It fails if
`NUM_PROXIES` is removed.

DRF caches settings in `api_settings` but reloads them on Django's
`setting_changed` signal, so `override_settings` works here. Worth knowing,
because the cached-settings trap catches people writing exactly this test.

## Alternatives rejected

- **Assume 1 from Railway's documentation.** The failure mode of guessing high
  is a global lockout, and platform docs are not a substitute for the chain the
  container actually receives.
- **Read it from an environment variable.** Tempting, because a mistake could
  then be corrected by a restart rather than a rebuild. Rejected: an env
  override reintroduces exactly the gap this ticket is closing, where the tested
  value and the live value are allowed to differ. It also cuts against the
  convention already set by the JWT lifetimes, which are hardcoded because a
  security-shaped constant should move through a PR.
- **`django-ipware`, or a custom `get_ident`.** A dependency and a code path to
  own, for something DRF already does correctly once told the hop count.
- **Keep the probe logging permanently behind a flag.** An extra knob, a public
  endpoint leaking proxy topology, and it is needed once per platform change.

## Blast radius

`get_ident` backs every `AnonRateThrottle` in the project, so this changes the
throttle identity for sign-in, refresh, and anything anonymous added later.
Nothing else reads `NUM_PROXIES`. No API change and no schema change, so
`api-client-drift` has nothing to say.

## Deliberately unhandled

- **The `LocMemCache` limitation.** Throttle state is per gunicorn worker and
  resets on every deploy. Recorded in MAC-27 and owned by E8. That makes the
  throttle weaker by a factor of the worker count; this bug makes it absent.
- **A future CDN in front of Railway.** It would change the hop count, which is
  what the doc 09 note exists to catch.

## Open questions

- Does Railway append to a client-supplied `X-Forwarded-For`, or replace it? PR
  1 answers this, and the third outcome in the table above would need a
  different fix entirely.
- `REMOTE_ADDR` was `100.64.0.2` on one probe and `100.64.0.3` on the next, so
  the proxy address is not stable. It does not change the fix, but it does mean
  a too-high `NUM_PROXIES` would produce a small pool of shared buckets rather
  than a single one — no better, and harder to recognise.
