"""URL routes for the accounts app, mounted at /api/auth/ by config.urls.

The URL tree and the Django app tree are allowed to differ. `accounts` owns
both `/api/auth/` and (later) `/api/users/`, because a session and a user are
different resources even though one app manages both.
"""

from django.urls import path

from accounts.views import SessionCreateView

app_name = "accounts"

urlpatterns = [
    # Empty path on purpose: this *is* `/api/auth/sessions/`. POST to a
    # collection already means "create one", so the URL needs no verb --
    # signing in creates a session, and signing out will delete one.
    path("sessions/", SessionCreateView.as_view(), name="session-create"),
]
