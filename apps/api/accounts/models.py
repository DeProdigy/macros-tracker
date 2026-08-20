from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models, transaction


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

    def create_apple_user(
        self,
        apple_user_id,
        email=None,
        is_private_email=None,
        real_user_status=None,
        **extra_fields,
    ):
        """Create a user who signs in with Apple, plus their Identity row.

        Separate from create_user rather than relaxing it. create_user hard-
        requires an email and always sets a password, which is what
        `createsuperuser` needs; loosening that guard to fit Apple would weaken
        superuser creation for every caller.

        email is optional because Apple does not guarantee it. The identity
        token normally carries an `email` claim, but it can be absent -- a
        stale app association, a Managed Apple ID, or a client that read the
        first-authorization-only `credential.email` property instead of the
        token. The join key is the Identity row (Apple's `sub`), never the
        email: a Hide My Email relay address can change or stop forwarding.

        Two rows, one transaction. Without atomic, a failure between the two
        writes leaves a user with no identity: they can never sign in, and
        their row does not block the retry either, so the next attempt forks a
        second account for the same person. Neither half is useful alone.
        """
        if not apple_user_id:
            raise ValueError("Apple users must have an apple_user_id.")

        with transaction.atomic():
            user = self.model(
                # normalize_email("") would give "", which is a real value that
                # would collide on the unique constraint. None must stay None.
                email=self.normalize_email(email) if email else None,
                **extra_fields,
            )
            # Not the same as a blank password: this writes an unusable
            # sentinel, so check_password() returns False for every input,
            # including the stored value itself. There is no password to guess.
            user.set_unusable_password()
            user.save(using=self._db)

            Identity.objects.using(self._db).create(
                user=user,
                provider=Identity.Provider.APPLE,
                subject=apple_user_id,
                is_private_email=is_private_email,
                real_user_status=real_user_status,
            )

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
    # No apple_user_id here. Identity below owns the provider subject, one row
    # per (provider, subject) pair -- see that model for why.
    #
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
        # email is nullable, so it cannot satisfy __str__'s str return type on
        # its own. The f-string terminates the chain. Deliberately does not
        # reach for an Identity: __str__ runs in list views and admin logs, and
        # a query per row there is how an N+1 gets built into a dunder.
        return self.email or f"user {self.pk}"


class Identity(models.Model):
    """One way a person proves who they are.

    Split out from User because identity and personhood are different things.
    A User is the account: their targets, their entries, their timezone. An
    Identity is a credential that resolves to that account. Today every user has
    exactly one, from Apple, so the two look interchangeable -- which is exactly
    why this is worth separating before the first real row exists rather than
    after.

    The forcing case is not a hypothetical second provider. It is an **app
    transfer**: move the app to another Apple developer team and Apple reissues
    every user's `sub`. With the subject inlined on User that migration rewrites
    the user table under live traffic. Here it inserts rows.

    Federated identity normalises this way everywhere -- Supabase's
    `auth.identities`, Django-allauth's `SocialAccount`. The shape is not
    clever; the mistake is skipping it because one provider fits in a column.
    """

    class Provider(models.TextChoices):
        APPLE = "apple", "Sign in with Apple"

    class RealUserStatus(models.IntegerChoices):
        """Apple's assessment of whether a real person is behind the request.

        Sent on the first authorization only. Values are Apple's, not ours.
        """

        UNSUPPORTED = 0, "Unsupported"
        UNKNOWN = 1, "Unknown"
        LIKELY_REAL = 2, "Likely real"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="identities",
    )
    provider = models.CharField(max_length=32, choices=Provider.choices)
    # The provider's stable subject claim -- Apple's `sub`. Opaque, and specific
    # to the (provider, app-team) pair that issued it.
    subject = models.CharField(max_length=255)

    # Whether the address Apple gave us is a Hide My Email relay.
    #
    # Three-valued on purpose. NULL means Apple did not tell us, which is not
    # the same as False. Defaulting to False would assert a real address we were
    # never told about, and the whole point of the field is knowing whether mail
    # to it can be relied on.
    #
    # Can change: a user may switch between their real address and a relay, so
    # this is refreshed whenever the claim is present.
    is_private_email = models.BooleanField(null=True, blank=True)

    # Apple's bot signal, captured once.
    #
    # Never updated after creation. Apple sends it on the first authorization
    # only, so a later token carries nothing -- and if a later token did carry
    # UNKNOWN, writing it would silently downgrade a stored LIKELY_REAL. The
    # field means "what Apple thought when this identity was first seen", and
    # that is a fact about one moment.
    real_user_status = models.IntegerField(
        choices=RealUserStatus.choices,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    # Last time *this credential* was used. Distinct from User.last_login, which
    # is person-level and also covers a superuser's admin password login. With
    # one provider the two move together; with two they answer the question
    # "which login did they actually use?", which is the first thing support
    # asks.
    last_authenticated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "identities"
        constraints = [
            # The pair, never `subject` alone. A subject is only unique *within*
            # a provider: Apple and any future provider mint opaque strings from
            # their own namespaces and nothing coordinates them. A unique index
            # on `subject` by itself would be a cross-provider collision that
            # fires once, years from now, and cannot be reproduced.
            models.UniqueConstraint(
                fields=["provider", "subject"],
                name="unique_provider_subject",
            ),
        ]

    def __str__(self):
        return f"{self.get_provider_display()}: {self.subject}"
