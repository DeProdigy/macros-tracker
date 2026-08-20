from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import UserChangeForm, UserCreationForm
from .models import Identity, User


class IdentityInline(admin.TabularInline):
    """Identities on the user page.

    An inline rather than a separate admin section because an identity is never
    interesting on its own -- the question is always "how does this person sign
    in?", which is a question about a user.
    """

    model = Identity
    extra = 0
    # Every field here is written by the sign-in path from claims Apple signed.
    # Editable, they would be a way to hand one person's account to another by
    # typing a different subject, from a form whose whole purpose is support
    # staff looking at accounts they do not own.
    readonly_fields = (
        "provider",
        "subject",
        "is_private_email",
        "real_user_status",
        "created_at",
        "last_authenticated_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # Adding one by hand would create a credential nobody holds.
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Custom forms (the defaults assume a username field).
    form = UserChangeForm
    add_form = UserCreationForm

    # BaseUserAdmin's defaults reference `username`, so override the bits that do.
    ordering = ("email",)
    # Reaches through the relation, because email is nullable. An Apple user who
    # hid their address has their identity subject as the only thing to search
    # on, so an email-only search cannot find them at all.
    search_fields = ("email", "identities__subject")
    list_display = (
        "email",
        # Which providers this person can sign in with. Annotated rather than
        # walked per row -- see get_queryset.
        "provider_list",
        "last_login",
        "is_staff",
        "is_superuser",
        "onboarding_completed",
    )
    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "onboarding_completed",
    )
    # auto_now_add / auth-managed fields can't be edited, so show them read-only.
    readonly_fields = ("last_login", "created_at")
    inlines = (IdentityInline,)

    # Layout of the change (edit) page.
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Profile",
            {
                "fields": (
                    "name",
                    "timezone",
                    "onboarding_completed",
                    "ai_calls_this_month",
                )
            },
        ),
        (
            "Settings",
            {
                # The four fields doc 05 moved out of onboarding. Listed here
                # because an admin fieldset is explicit: a field absent from
                # this tuple is invisible in the admin no matter what the model
                # says, and support cannot answer "what goal did they set?"
                "fields": (
                    "goal_weight_kg",
                    "goal_timeline_weeks",
                    "training_days_per_week",
                    "dietary_constraints",
                ),
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

    def get_queryset(self, request):
        """Prefetch identities so the changelist does not issue one query per row.

        `provider_list` reads a related manager. Without this, a page of 100
        users is 101 queries -- the classic N+1, and the admin is where it hides
        best because nobody load-tests it.
        """
        return super().get_queryset(request).prefetch_related("identities")

    @admin.display(description="Sign-in methods")
    def provider_list(self, obj: User) -> str:
        # Iterates the prefetched cache rather than filtering, which would issue
        # a fresh query and defeat the prefetch above.
        return ", ".join(i.get_provider_display() for i in obj.identities.all()) or "—"
