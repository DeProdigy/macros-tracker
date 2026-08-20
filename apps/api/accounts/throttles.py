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
