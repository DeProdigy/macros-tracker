"""URL routes for the targets app, mounted at /api/targets/ by config.urls."""

from django.urls import path

from targets.views import CurrentTargetVersionView, TargetVersionListCreateView

app_name = "targets"

urlpatterns = [
    # Empty path on purpose: this *is* `/api/targets/`. POST to a collection
    # already means "create one", so the URL needs no verb.
    path("", TargetVersionListCreateView.as_view(), name="list-create"),
    # Must stay above any future *untyped* or `<str:pk>/` detail route, which
    # would swallow the literal `current` as an id.
    #
    # An `<int:pk>/` route cannot: the converter matches digits only, so
    # `current` never reaches it and the ordering stops mattering. Review pointed
    # that out, and the mutation test proving the hazard uses `<str:pk>/` for
    # exactly that reason. Give the detail route `<int:pk>/` when it arrives and
    # the collision cannot happen at all.
    path("current/", CurrentTargetVersionView.as_view(), name="current"),
]
