from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models


class UserManager(BaseUserManager["User"]):
    """Manager for the custom User.

    Django's default manager assumes a ``username`` field, so a custom user
    keyed on email needs its own. These two methods are what ``User.objects``
    and ``createsuperuser`` call.
    """

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        # normalize_email lowercases the domain part (Foo@EXAMPLE.com -> Foo@example.com)
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        # set_password hashes the password; never assign user.password directly.
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        # Guard against a superuser being created without the right flags.
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model, keyed on email.

    AbstractBaseUser supplies the password/auth machinery (no identity fields);
    PermissionsMixin adds is_superuser, groups, and permission checks used by
    the admin and DRF. See plan doc 02 for the field rationale.
    """

    # --- identity ---
    email = models.EmailField(unique=True)

    # --- profile / domain fields (plan doc 02) ---
    is_email_verified = models.BooleanField(default=False)
    # Apple's stable subject claim. null so non-Apple users don't collide on the
    # unique constraint (in Postgres, NULLs are never equal to each other).
    apple_user_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    # IANA timezone name (e.g. "America/New_York"), never a numeric offset —
    # offsets break across DST.
    timezone = models.CharField(max_length=64, default="UTC")
    onboarding_completed = models.BooleanField(default=False)
    # Monthly AI-call quota counter (reset externally). Never negative.
    ai_calls_this_month = models.PositiveIntegerField(default=0)
    # Soft delete: set instead of hard-deleting the row.
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # --- auth flags required by Django (not listed in plan doc 02) ---
    # is_active: auth backends reject users with is_active=False.
    is_active = models.BooleanField(default=True)
    # is_staff: gates Django admin login (is_superuser alone is not enough).
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    # Log in with email; password is prompted automatically. REQUIRED_FIELDS is
    # the *extra* prompts createsuperuser asks for beyond email + password —
    # none here (and it must never include USERNAME_FIELD itself).
    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email
