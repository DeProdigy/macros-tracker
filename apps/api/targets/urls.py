"""URL routes for the targets app, mounted at /api/targets/ by config.urls."""

from django.urls import path

from targets.views import CurrentTargetVersionView, TargetVersionListCreateView

app_name = "targets"

urlpatterns = [
    # Empty path on purpose: this *is* `/api/targets/`. POST to a collection
    # already means "create one", so the URL needs no verb.
    path("", TargetVersionListCreateView.as_view(), name="list-create"),
    # Must stay above any future `<int:pk>/`, or the literal never matches. Give
    # that detail route a typed converter when it appears, so the two cannot
    # collide on a request that happens to look like both.
    path("current/", CurrentTargetVersionView.as_view(), name="current"),
]
