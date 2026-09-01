from django.urls import path

from .views import FoodAnalysisCreateView

urlpatterns = [path("", FoodAnalysisCreateView.as_view(), name="food-analysis-create")]
