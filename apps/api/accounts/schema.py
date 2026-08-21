"""Schema customisation for the accounts app.

One class, for one endpoint, because of one gap between two specifications.
"""

from typing import Any

from drf_spectacular.openapi import AutoSchema


class RequestBodyOnDeleteAutoSchema(AutoSchema):
    """Emit a `requestBody` for DELETE, which drf-spectacular otherwise drops.

    `AutoSchema._get_request_body` returns None for anything outside PUT, PATCH
    and POST. That is a reasonable default -- RFC 9110 says a DELETE body has no
    defined semantics, and most DELETEs that carry one are a design mistake.

    Sign-out is the case where it is not. The only revocable credential in this
    scheme is the refresh token: nothing on the access path consults a
    blacklist, so an access token cannot be revoked, and the refresh token is
    not derivable from the `Authorization` header. It has to travel in the
    request, and the two alternatives to a body are both worse -- a query string
    puts a live credential into every access log and proxy cache, and a custom
    header invents a private protocol for one endpoint.

    Without this, `@extend_schema(request=...)` on the view is silently ignored,
    `openapi.json` describes a bodyless DELETE, and Orval generates
    `deleteCurrentSession()` with no argument. The mobile client then cannot
    sign out through the generated client at all -- and nothing fails loudly,
    which is the part that makes it worth a class.

    Scoped to the one view that needs it rather than set as the project-wide
    `DEFAULT_SCHEMA_CLASS`. A global switch would quietly bless a DELETE body
    everywhere, and the next one to appear should have to argue for itself the
    way this one did.
    """

    def _get_request_body(self, direction: str = "request") -> Any:
        if self.method != "DELETE":
            return super()._get_request_body(direction)

        # Borrow POST's path through the base implementation. Swapping the
        # attribute is narrower than copying forty lines of media-type and
        # example handling that would then rot against the next release.
        self.method = "POST"
        try:
            return super()._get_request_body(direction)
        finally:
            self.method = "DELETE"
