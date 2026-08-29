from django.contrib import admin

from .models import TargetVersion


@admin.register(TargetVersion)
class TargetVersionAdmin(admin.ModelAdmin):
    """Read-only, and that is the whole point.

    Editing a version in place contradicts the model: a `DailyLog` already
    points at this row, so changing the numbers here silently rewrites history
    for every day that referenced it. The admin is exactly where someone would
    do that by accident while trying to help a user.

    Adding is blocked for the same reason it is elsewhere in this project --
    a row created by hand skips the clamp in MAC-39 and the `onboarding_completed`
    write in MAC-47, so it would be a target set no code path can produce.

    Deleting stays available. Support occasionally needs to undo a bad row, and
    unlike an edit it is visible: the version disappears rather than quietly
    holding different numbers.
    """

    list_display = ("user", "calories", "protein_g", "fiber_g", "source", "effective_from")
    list_filter = ("source",)
    search_fields = ("user__email",)
    # Reaches across the FK on every row otherwise, once per version listed.
    list_select_related = ("user",)
    date_hierarchy = "effective_from"

    readonly_fields = (
        "user",
        "calories",
        "protein_g",
        "fiber_g",
        "source",
        "ai_rationale",
        "effective_from",
        "created_at",
    )

    def has_add_permission(self, request) -> bool:
        return False
