"""URL routes for the uploads app, mounted at /api/uploads/ by config.urls."""

from django.urls import path

from uploads.views import PresignUploadView

app_name = "uploads"

urlpatterns = [
    # Empty path on purpose: this *is* `/api/uploads/`. Shipped as `presign/`
    # in MAC-19 and renamed in the 20 Aug 2026 route audit — `presign` named
    # the mechanism, and POST to a collection already means "create one".
    # The operation_id stays `presignUpload`: URLs name resources, operation
    # ids name operations, and operations are allowed verbs.
    path("", PresignUploadView.as_view(), name="create"),
]
