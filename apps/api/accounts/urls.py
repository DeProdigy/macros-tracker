"""URL routes for the accounts app, mounted at /api/auth/ by config.urls.

The URL tree and the Django app tree are allowed to differ. `accounts` owns
both `/api/auth/` and (later) `/api/users/`, because a session and a user are
different resources even though one app manages both.
"""

from django.urls import path

from accounts.views import CurrentSessionView, SessionCreateView, SessionRefreshView

app_name = "accounts"

urlpatterns = [
    # Empty path on purpose: this *is* `/api/auth/sessions/`. POST to a
    # collection already means "create one", so the URL needs no verb --
    # signing in creates a session, and signing out will delete one.
    path("sessions/", SessionCreateView.as_view(), name="session-create"),
    # The one surviving verb in this API. Token exchange is the exception the
    # route conventions name: the credential presented is not the resource
    # addressed, and OAuth 2 landed on a single token endpoint for the reason.
    # Declared before `sessions/current/` for readability only -- these are
    # literal segments, so no ordering hazard exists between them.
    path("sessions/refresh/", SessionRefreshView.as_view(), name="session-refresh"),
    # Named singleton: the caller's own session, which has no id it could use.
    # DELETE here is signing out. There is deliberately no `sessions/` list and
    # no `sessions/<id>/` -- a client cannot enumerate or address anyone's
    # sessions, including its own.
    path("sessions/current/", CurrentSessionView.as_view(), name="session-current"),
]
