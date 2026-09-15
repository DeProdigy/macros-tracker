from django.urls import path

from .views import (
    EntryDetailView,
    EntryItemDetailView,
    EntryItemListCreateView,
    EntryListCreateView,
)

urlpatterns = [
    path("", EntryListCreateView.as_view(), name="entry-list"),
    path("<int:pk>/", EntryDetailView.as_view(), name="entry-detail"),
    path("<int:entry_id>/items/", EntryItemListCreateView.as_view(), name="entry-item-list"),
    path(
        "<int:entry_id>/items/<int:pk>/",
        EntryItemDetailView.as_view(),
        name="entry-item-detail",
    ),
]
