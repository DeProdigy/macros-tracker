from django.urls import path

from .views import DayDetailView, DayListView

urlpatterns = [
    path("", DayListView.as_view(), name="day-list"),
    path("<str:local_date>/", DayDetailView.as_view(), name="day-detail"),
]
