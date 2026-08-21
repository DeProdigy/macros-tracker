"""Rate limits for the sign-in endpoint.

Two scopes rather than one, which is DRF's own documented pattern. A single
flat rate has to choose between blocking a human who taps the button twice and
leaving room for a script: 10/min alone permits 600/hour, and 60/hour alone
rejects the second tap in a minute. Together they allow a burst and still cap
the day.

Worth being clear about what these are for. Sign in with Apple has no password
to guess, and forged tokens are stopped by the signature check in
`verify_apple_identity_token`, not here. **The throttle is not the security
control.** It exists for cost and denial of service, which is why it can afford
to be generous rather than tight.

Known limitation: DRF throttling needs a cache, and there is no Redis. This
lands on the per-process LocMemCache declared in settings, so the limit is per
gunicorn worker and resets on every deploy. Acceptable against a single-user
MVP, and a decision rather than an accident. E8 owns the real fix.
"""

from rest_framework.throttling import AnonRateThrottle


class SignInBurstThrottle(AnonRateThrottle):
    """Short window. Catches a stuck retry loop in the client."""

    scope = "signin-burst"


class SignInSustainedThrottle(AnonRateThrottle):
    """Long window. Wide enough for a household behind one NAT."""

    scope = "signin-sustained"


class RefreshThrottle(AnonRateThrottle):
    """Rate limit for the refresh endpoint.

    One scope, where sign-in has two, because the shape of legitimate traffic is
    different. Sign-in is a human tapping a button, so a burst limit and a daily
    limit answer two different questions about the same caller. Refreshing is a
    machine on a timer: with a 15-minute access lifetime one device needs about
    four calls an hour and never needs two in a row. A single generous per-
    minute cap catches the failure that actually happens here, which is a client
    stuck in a retry loop, and nothing is gained by also capping the day.

    Generous on purpose. This throttle keys on IP, so a household or an office
    behind one address shares it, and the endpoint every signed-in client must
    reach is the worst possible place for a false positive. It is sized to stop
    a hot loop, not to be tight.

    Not the security control, same as the sign-in throttles. A refresh token is
    already a credential and there is nothing to brute force -- rejecting an
    invalid token costs a signature check. This is here for cost, and because an
    unauthenticated endpoint with no limit at all is a decision nobody should
    make by omission. MAC-36's proxy problem applies here too: unreliable client
    attribution weakens the limit, it does not make it pointless.
    """

    scope = "refresh"
