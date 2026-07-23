from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import UserChangeForm, UserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Custom forms (the defaults assume a username field).
    form = UserChangeForm
    add_form = UserCreationForm

    # BaseUserAdmin's defaults reference `username`, so override the bits that do.
    ordering = ("email",)
    search_fields = ("email",)
    list_display = (
        "email",
        "is_staff",
        "is_superuser",
        "is_email_verified",
        "onboarding_completed",
    )
    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "is_email_verified",
        "onboarding_completed",
    )
    # auto_now_add / auth-managed fields can't be edited, so show them read-only.
    readonly_fields = ("last_login", "created_at")

    # Layout of the change (edit) page.
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Profile",
            {
                "fields": (
                    "timezone",
                    "apple_user_id",
                    "is_email_verified",
                    "onboarding_completed",
                    "ai_calls_this_month",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Dates", {"fields": ("last_login", "created_at", "deleted_at")}),
    )

    # Layout of the add (create) page.
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
