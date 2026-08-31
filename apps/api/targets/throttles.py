"""Throttles for `/api/targets/`.

A `UserRateThrottle`, not the `AnonRateThrottle` pattern `accounts` uses. That
one keys on IP because sign-in has no user yet. Every route here is
authenticated, so the user id is the honest key, and an office behind one
address does not share a bucket.

The point is the same as `accounts/throttles.py` makes: **a throttle is a cost
guard, not a security control.** It bounds the damage a broken client does. It
does not stop anyone determined.
"""

from rest_framework.throttling import UserRateThrottle


class TargetProposalThrottle(UserRateThrottle):
    """Bounds a client stuck in a retry loop on the proposal endpoint.

    Cheap today: pure arithmetic, no network, no writes. The limit exists
    because the shape of a retry loop does not depend on how cheap the endpoint
    is, and a mobile client that recomputes on every keystroke would find this
    long before anyone read the logs.

    Sized generously. A real user answers six questions once and may recompute a
    handful of times from Settings, so 30 a minute is far above any honest
    session while still catching a loop.
    """

    scope = "target-proposal"
