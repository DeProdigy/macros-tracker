"""URL routes for the uploads app, mounted at /api/uploads/ by config.urls."""

from django.urls import path

from uploads.views import PresignUploadView

app_name = "uploads"

urlpatterns = [
    path("presign/", PresignUploadView.as_view(), name="presign"),
]
