from django.contrib import admin
from django.http import HttpRequest

from .models import TargetVersion


@admin.register(TargetVersion)
class TargetVersionAdmin(admin.ModelAdmin):
    """Superusers can add and edit. Staff can only look.

    **Editing a row here rewrites history.** A `DailyLog` captures its
    `target_version` FK when the day is created, so changing these numbers
    silently changes what every day pointing at this row was measured against.
    That is the one thing the append-only model exists to prevent, and the admin
    is exactly where someone does it by accident while trying to help a user.

    The safer shape is a new version rather than an edit, and that stays true
    even for a superuser. This form is the escape hatch for the case the API
    cannot express, not the normal way to change someone's targets.

    Gated by permission rather than by `readonly_fields`. Listing every field in
    a read-only tuple works today and is an allowlist maintained by hand: add a
    column in a later ticket, forget this file, and that column is quietly
    editable with no test and no CI job to notice. `has_change_permission`
    states the rule once and covers every field that will ever exist.

    A hand-added row skips MAC-39's clamp and MAC-47's `onboarding_completed`
    write, so it is a target set no code path can otherwise produce. Superuser
    only, for the same reason the change form is.
    """

    list_display = ("user", "calories", "protein_g", "fiber_g", "source", "effective_from")
    list_filter = ("source",)
    search_fields = ("user__email",)
    # Reaches across the FK on every row otherwise, once per version listed.
    list_select_related = ("user",)
    date_hierarchy = "effective_from"

    # `auto_now_add`, so Django ignores anything the form sends for it. Listed
    # so the form says that rather than offering a field that silently does
    # nothing.
    readonly_fields = ("created_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_superuser)

    def has_change_permission(self, request: HttpRequest, obj: TargetVersion | None = None) -> bool:
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request: HttpRequest, obj: TargetVersion | None = None) -> bool:
        # Deleting is the least dangerous of the three, because unlike an edit
        # it is visible. The version disappears rather than quietly holding
        # different numbers. What a `DailyLog` referencing it should then do is
        # E4's call, when that FK gets its `on_delete`.
        return bool(request.user.is_superuser)
