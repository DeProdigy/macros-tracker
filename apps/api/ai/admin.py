from django.contrib import admin
from django.http import HttpRequest

from .models import FoodAnalysisCall


@admin.register(FoodAnalysisCall)
class FoodAnalysisCallAdmin(admin.ModelAdmin):
    """Operational evidence is inspectable but never editable in admin."""

    list_display = (
        "user",
        "status",
        "provider",
        "model",
        "provider_called_at",
        "quota_debited_at",
        "estimated_cost_usd",
    )
    list_filter = ("status", "provider", "model")
    search_fields = ("user__email", "provider_request_id")
    list_select_related = ("user",)
    date_hierarchy = "created_at"

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: FoodAnalysisCall | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: FoodAnalysisCall | None = None
    ) -> bool:
        return False
