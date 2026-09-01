from django.urls import path

from .views import DayDetailView

urlpatterns = [path("<str:local_date>/", DayDetailView.as_view(), name="day-detail")]
