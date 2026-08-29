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
header, so the identity carries Railway's own address as well as the caller's.

The ticket assumed the caller could forge its left-hand end and mint a fresh
cache key per request. **The measurement disproved that**; see the section
below. The bug that was really live is narrower and is written up there.

Locally there is no proxy, no header, and `get_ident` returns `REMOTE_ADDR`.
The bug exists only where it matters, which is why the tests are green.

The general form is worth naming, because it will come back: **a control keyed
on client identity is only as trustworthy as the proxy configuration under it.**
`SECURE_PROXY_SSL_HEADER` in `production.py` already draws exactly this trust
boundary for the HTTPS decision. This ticket draws it for a second header.

## Why this is not one line

DRF counts **backwards from the right-hand end** of the chain:
`addrs[-min(n, len(addrs))]`. That direction is the whole design. Each proxy
appends the address it received the connection from, so entries near the right
were written by infrastructure and entries near the left were written by the
caller. Counting from the right walks inward through machines that cannot lie;
counting far enough walks out into text the caller supplied.

Both directions of a wrong value are bad, and they fail in opposite ways:

- **Too low** stops short of the client and lands on a proxy's own address,
  which is the same for everybody. Every caller shares one bucket, and ten
  sign-ins a minute across the whole world locks the rest out. This reads as an
  outage rather than as a bug.
- **Too high** reaches past the client into the forged left-hand end. A caller
  who pads the header with enough junk entries is identified by its own junk,
  and the original bypass is back.

Note the direction here, because the Linear ticket states it the other way
round. The behaviour above is what `rest_framework/throttling.py` actually does;
the ticket's version would put the wrong explanation into the code comment.

Unset is a third case and is not on this scale at all: `get_ident` falls to its
last line and uses the whole chain, forged portion included.

Platforms also disagree about whether the true client sits at the left or the
right. So the number gets measured from a real deployed request rather than read
off a documentation page.

## Approach: measure first, then fix

Two PRs, deliberately. PR 1 turned on the logging. PR 2, this one, sets the
value and turns the logging back off.

Two deploys for a one-line setting is slower than guessing. Guessing low
produces a lockout on the endpoint every client must reach. The extra deploy was
cheap against that, and it turned out to be the only thing that could have
caught what the header actually does.

## What the measurement found

Run 29 Aug 2026 against `https://api-production-2884.up.railway.app/api/ping/`
from a machine whose public address was `108.6.37.101`.

| Forged entries sent | Chain the container received |
| --- | --- |
| none | `108.6.37.101, 152.233.47.68` |
| `1.1.1.1` | `108.6.37.101, 152.233.47.67` |
| `9.9.9.9, 8.8.8.8` | `108.6.37.101, 152.233.47.66` |
| five entries | `108.6.37.101, 152.233.47.65` |

**Railway replaces the header rather than appending to it.** Not one forged
entry survived, and the chain was two entries long regardless of what went in.
So `NUM_PROXIES = 2` selects `addrs[-2]`, which is the caller.

That kills the arithmetic rule this plan carried into PR 1
(`NUM_PROXIES = entries logged - entries forged`). The rule assumed appending
and returns 0 here, which is wrong. Recorded rather than deleted, because the
rule is right for a platform that appends and the failure was assuming which
kind of platform this is. Only the log could tell them apart.

Two consequences, both the opposite of what the ticket said:

- **The identity is not forgeable.** Railway overwrites what the caller sends.
  The bypass in the ticket title does not exist. Worth saying plainly, because
  the throttle also is not the security control (see `accounts/throttles.py`) —
  Apple sign-in has no password to guess and a forged token dies at the
  signature check. The throttle is a cost and denial-of-service guard.
- **The real bug is bucket fragmentation.** Unset, the identity was the whole
  chain, and the right-hand Railway address rotates. `152.233.47.65` through
  `.69` all appeared within five minutes, and older log lines carry
  `79.127.177.114` and `152.233.76.9`. One caller was therefore spread across
  several buckets and got a multiple of the intended allowance. Real, worth
  fixing, and much smaller than filed.

**Too low is the dangerous direction; too high is now unreachable.** With the
chain fixed at two entries, `addrs[-min(n, len(addrs))]` clamps, so any `n`
above 2 gives the same answer as 2. `n = 1` selects the shared Railway address
and rate-limits the whole world into one bucket. Both directions still have a
test.

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

The plan originally described a test that forges a left-hand entry and asserts
it is ignored. The measurement rules that shape out: Railway strips it, so the
request cannot arrive. A test asserting against an impossible request passes
forever and guards nothing.

The two tests that shipped use the measured shape instead, both in
`accounts/tests/test_sessions.py`:

- One caller, rotating Railway address, must stay in one bucket. This is the
  bug that was live.
- Two callers behind the same Railway address must not share a bucket. This
  catches `NUM_PROXIES = 1`, which reads as an outage rather than as a bug.

Mutation-checked all three ways. Comment the setting out and the first test
fails. Set it to 1 and both fail. Set it to 2 and both pass.

DRF caches settings in `api_settings` but reloads them on Django's
`setting_changed` signal, so `override_settings` works here. Worth knowing,
because the cached-settings trap catches people writing exactly this test.

## Alternatives rejected

- **Assume 1 from Railway's documentation.** Guessing low locks every caller
  into one bucket and guessing high leaves the bypass open, so platform docs are
  not a substitute for the chain the container actually receives.
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

## Open questions, answered

- **Does Railway append or replace?** Replace. Four probes, none of the forged
  entries survived.
- **Is `REMOTE_ADDR` stable?** No, and neither is the right-hand chain entry.
  That instability is the bug rather than a footnote to it: it is what split one
  caller across buckets.
- **`base.py` or `production.py`?** `base.py`, departing from the ticket. The
  reasoning is the section above. No ruling came back, so this went the way the
  plan argued.
