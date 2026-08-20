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

    def create_apple_user(self, apple_user_id, email=None, **extra_fields):
        """Create a user who signs in with Apple and has no password.

        Separate from create_user rather than relaxing it. create_user hard-
        requires an email and always sets a password, which is what
        `createsuperuser` needs; loosening that guard to fit Apple would weaken
        superuser creation for every caller.

        email is optional because Apple does not guarantee it. The identity
        token normally carries an `email` claim, but it can be absent -- a
        stale app association, a Managed Apple ID, or a client that read the
        first-authorization-only `credential.email` property instead of the
        token. The join key is apple_user_id (Apple's `sub`), never the email:
        a Hide My Email relay address can change or stop forwarding.
        """
        if not apple_user_id:
            raise ValueError("Apple users must have an apple_user_id.")
        user = self.model(
            apple_user_id=apple_user_id,
            # normalize_email("") would give "", which is a real value that
            # would collide on the unique constraint. None must stay None.
            email=self.normalize_email(email) if email else None,
            **extra_fields,
        )
        # Not the same as a blank password: this writes an unusable sentinel, so
        # check_password() returns False for every input, including the stored
        # value itself. There is no password to guess.
        user.set_unusable_password()
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
    # Nullable because Apple does not guarantee an email, and a NOT NULL column
    # would force the sign-in path to either reject a legitimate user or invent
    # a placeholder. Still unique: Postgres treats NULLs as distinct, so any
    # number of Apple users without an email coexist.
    #
    # This is the general shape for any federated provider. The subject
    # identifier is the only claim guaranteed to arrive; everything else is
    # optional and consent-gated, so a NOT NULL on it would bake an assumption
    # about someone else's consent screen into our schema.
    email = models.EmailField(unique=True, null=True, blank=True)

    # --- profile / domain fields (plan doc 02) ---
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
        # email is nullable and apple_user_id always has been, so neither alone
        # satisfies __str__'s str return type. The f-string terminates the chain.
        return self.email or self.apple_user_id or f"user {self.pk}"
