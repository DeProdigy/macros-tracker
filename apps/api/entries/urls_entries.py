from django.urls import path

from .views import EntryItemDetailView, EntryItemListCreateView, EntryListCreateView

urlpatterns = [
    path("", EntryListCreateView.as_view(), name="entry-list"),
    path("<int:entry_id>/items/", EntryItemListCreateView.as_view(), name="entry-item-list"),
    path(
        "<int:entry_id>/items/<int:pk>/",
        EntryItemDetailView.as_view(),
        name="entry-item-detail",
    ),
]
