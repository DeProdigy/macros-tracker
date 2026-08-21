"""URL routes for the user resource, mounted at /api/users/ by config.urls.

A second module in the same app, because `accounts` owns two URL prefixes. The
alternative -- one module exporting two lists -- hides the second mount inside a
file whose name says `urls`, and `include()` reads better against a module than
against an imported list.

Why the user is not under `/api/auth/`: a user is a user whether you are reading
it, updating it, or deleting it. `GET /api/auth/me/` alongside
`DELETE /api/auth/account/` addressed one row under two names, which is what the
20 Aug 2026 route audit removed. See the Decision Log.
"""

from django.urls import path

from accounts.views import CurrentUserView

app_name = "users"

urlpatterns = [
    # Named singleton, and one of the exceptions the conventions allow: a client
    # cannot address itself by id, and the server genuinely owns which user a
    # bearer token resolves to.
    #
    # When a `users/<int:pk>/` route ever appears it must be declared *after*
    # this line and must use the typed converter, or `me` matches the detail
    # route and 404s on a user who is right there.
    path("me/", CurrentUserView.as_view(), name="current"),
]
