from decimal import Decimal

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.validators import MaxValueValidator, MinValueValidator
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


# The weight band `targets.services` can compute a calorie range for. Neither
# number is a general sanity bound: outside them the suggested calorie floor and
# ceiling cross and the range raises.
#
# It inverts at both ends. At the bottom the fixed sex floor passes the per-pound
# ceiling at 82.67 lb. At the top the ceiling stops at 5,000 kcal while the floor
# keeps climbing, so they meet again at 501.05 lb. Enforcing both here is what
# makes a bad weight a 400 at the edge rather than a 500 from the range guard.
#
# The first version of this used 85 to 1000, and 1000 was picked as "catches a
# typo" without checking the top crossing. Review found it: `PATCH` with 600 lb
# was accepted and then crashed. A typo is exactly how you get there, since 1000
# is what a mistyped 100.0 looks like.
#
# Duplicated from MINIMUM_SUPPORTED_WEIGHT_LB and MAXIMUM_SUPPORTED_WEIGHT_LB
# rather than imported, because `accounts` importing `targets` inverts the app
# dependency doc 02 sets out. `targets/tests/test_units.py` asserts they agree.
WEIGHT_FLOOR_LB = Decimal("85")
WEIGHT_CEILING_LB = Decimal("500")


class Sex(models.TextChoices):
    """Biological sex, as Mifflin-St Jeor and the calorie floors need it.

    Biological rather than gender, and the distinction matters here: the formula
    is fitted to body composition, not to identity. Doc 15 labels the question
    accordingly.

    **Mirrored by `targets.services.Sex`**, which is a plain `StrEnum` because
    that module is pure functions with no Django in it. The values must match,
    and `targets/tests/test_units.py` asserts they do rather than leaving it to
    whoever edits one of them next.

    This is the canonical one. `accounts` owns the column, and `targets`
    importing it would invert the app dependency doc 02 sets out.
    """

    FEMALE = "female", "Female"
    MALE = "male", "Male"


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

    # Display name, and the one field on this model we cannot verify.
    #
    # Apple does not put a name in the identity token -- their discovery document
    # lists every claim they send, and there is none. `fullName` arrives on the
    # client-side credential, on the first authorization only, and never again.
    # So the client forwards it and we take its word for it.
    #
    # That is acceptable for a display name: it is the user's own name and
    # nobody is harmed by them typing a different one. It is NOT acceptable as
    # an input to anything security-relevant, and nothing may ever gate on it.
    # Email is the opposite case and keeps the stricter rule -- read from the
    # verified claims, never from a client field (doc 04).
    #
    # blank + default="" rather than null. A nullable CharField gives two ways
    # to say "empty", and every reader then has to handle both.
    name = models.CharField(max_length=255, blank=True, default="")

    # --- profile / domain fields (plan doc 02) ---
    # No apple_user_id here. Identity below owns the provider subject, one row
    # per (provider, subject) pair -- see that model for why.
    #
    # IANA timezone name (e.g. "America/New_York"), never a numeric offset —
    # offsets break across DST.
    timezone = models.CharField(max_length=64, default="UTC")
    # Server-derived, and the only thing the launch gate reads.
    #
    # It turns true when the user's first TargetVersion is written, and no
    # client can set it: `UserSettingsSerializer` omits it and a test pins that.
    # A client that could assert it could walk past onboarding by claiming to
    # have finished it.
    #
    # **Onboarding is a hard gate.** Ruled 30 Aug 2026, reversing the 20 Aug
    # sequencing. The six questions come first and there is no skip, so a user
    # with no targets has no way into the app and every logged day has targets
    # to measure against. The reversed order also removed the reason for a
    # nullable `DailyLog.target_version`. See the Decision Log.
    onboarding_completed = models.BooleanField(default=False)

    # --- onboarding answers worth keeping (doc 05) ---
    # Two of the six questions, stored because the answers outlive the flow that
    # asked them.
    #
    # The other four are transient: age, height, goal and activity feed
    # Mifflin-St Jeor once and are never needed again. These two are different.
    # Editing targets in Settings weeks later needs both, and without them the
    # server has no way to bound a protein target it is being asked to store.
    # Before this, the app asked for weight and then threw it away, while
    # keeping the *goal* weight. Storing the target and forgetting the number it
    # is measured against is backwards.
    #
    # "Not answered" is a real state: doc 26 makes exiting onboarding early a
    # supported end, so a user can reach Settings without ever being asked.
    #
    # blank + default="" rather than null, matching `name` and
    # `dietary_constraints` above and ruff's DJ001. A nullable CharField gives
    # two ways to spell "empty" and every reader then has to handle both. The
    # numeric fields below are genuinely nullable, because 0 lb is a value rather
    # than an absence.
    sex = models.CharField(max_length=16, choices=Sex.choices, blank=True, default="")

    current_weight_lb = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(WEIGHT_FLOOR_LB), MaxValueValidator(WEIGHT_CEILING_LB)],
    )

    # --- settings (doc 05) ---
    # The four questions doc 05 moved *out* of onboarding. They improve target
    # quality and none of them blocks computing targets, so onboarding never
    # asks and `PATCH /api/users/me/` (MAC-28) is the only thing that writes
    # them.
    #
    # All four are nullable/blank because "not answered" is a real, common, and
    # permanent state -- most users will never fill any of these in. A default
    # would be a fabricated answer, and target generation cannot tell a
    # fabricated 3 training days from a stated one.
    #
    # Units are in the field names, following protein_g/fiber_g in doc 02. A
    # bare `goal_weight` is the column that eventually receives pounds from one
    # call site and kilos from another.
    #
    # **Pounds, corrected 30 Aug 2026.** This shipped as `goal_weight_kg` in
    # MAC-28, before the US units decision. Every screen that will ever write it
    # shows pounds, so the column was one call site away from receiving them
    # under a name that said otherwise. That is the exact failure the suffix
    # exists to prevent, so the suffix was right and the unit was wrong.
    #
    # Same band as `current_weight_lb` above, and review is why. The first
    # version carried 44 to 880 across from the old 20 to 400 kg, so a goal of
    # 44 lb passed while a current weight of 44 lb failed. Same measurement, same
    # unit, opposite answers, and no comment explaining it because there was no
    # reason. Nobody had picked 44 or 880 in pounds; the conversion just landed
    # there.
    goal_weight_lb = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(WEIGHT_FLOOR_LB), MaxValueValidator(WEIGHT_CEILING_LB)],
    )
    # Weeks, not a target date. A date goes stale on its own and then reads as
    # a missed deadline; a duration stays meaningful whenever it is read.
    goal_timeline_weeks = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(104)],
    )
    training_days_per_week = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(7)],
    )
    # Free text, not an enum of diets. This feeds an AI prompt (doc 08), which
    # reads "no dairy, allergic to shellfish" as well as it reads "vegan" --
    # and a fixed enum would have to be extended for every constraint a real
    # person has. Bounded because it lands in a prompt: max_length on a
    # TextField is validation only, no column change.
    #
    # blank + default="" rather than null, the same call as `name` above: a
    # nullable text column gives two ways to say "empty" and every reader then
    # has to handle both.
    dietary_constraints = models.TextField(max_length=500, blank=True, default="")
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
