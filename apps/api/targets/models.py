from django.conf import settings
from django.db import models


class TargetVersionQuerySet(models.QuerySet["TargetVersion"]):
    def for_user(self, user) -> "TargetVersionQuerySet":
        return self.filter(user=user)

    def current(self, user) -> "TargetVersion | None":
        """The version in effect now, or None if the user has never set targets.

        A method rather than a stored `is_current` boolean. A boolean would be a
        second source of truth that can disagree with the ordering, and keeping
        it accurate means writing to the previous row on every change -- which
        is the in-place update this whole model exists to avoid.

        Returns None rather than raising. A user with no targets is a supported
        state (they logged a meal and skipped onboarding), not an exception, and
        `.latest()` would force every caller to wrap this in a try block.
        """
        return self.for_user(user).first()


class TargetVersion(models.Model):
    """One set of daily macro targets, valid from a point in time.

    **Append-only. Never updated in place.** Adjusting targets writes a new row.
    A `DailyLog` captures its `target_version` FK when the day is created, so
    changing targets today cannot rewrite last week's progress.

    This is the slowly-changing-dimension pattern. Worth naming, because "why
    did last month's numbers change?" is an entire bug class it removes. The
    cost is that "what are my targets?" becomes a query rather than a column
    read, which is the trade every version-tracked table makes.
    """

    class Source(models.TextChoices):
        ONBOARDING_AI = "onboarding_ai", "Onboarding (AI proposal)"
        MANUAL = "manual", "Manual edit"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="target_versions",
    )

    calories = models.IntegerField()
    protein_g = models.IntegerField()
    fiber_g = models.IntegerField()

    source = models.CharField(max_length=32, choices=Source.choices)

    # The model's explanation, shown to the user under WHY THESE NUMBERS.
    #
    # Blank rather than null, per Django's own guidance on text fields: a
    # nullable CharField gives two ways to spell "empty" and every reader then
    # has to handle both. A manual edit has no rationale and stores "".
    ai_rationale = models.TextField(blank=True)

    # The calendar date these targets start applying to.
    #
    # **No default, deliberately.** The obvious `timezone.now().date()` would be
    # wrong: `User.timezone` is "UTC" for everyone until MAC-48 ships, so a
    # caller in Los Angeles saving at 5pm would get tomorrow's date. Doc 02
    # already solved this for DailyLog by having the client send its own
    # `local_date`, and the endpoint in MAC-40 follows that same path. Baking a
    # server-side default in here would hide a timezone bug inside a column.
    effective_from = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

    objects = TargetVersionQuerySet.as_manager()

    class Meta:
        # Newest first, which is what every reader wants: the current version,
        # and the history screen's card list.
        #
        # `-id` is not decoration. "Latest by created_at" is ambiguous the moment
        # two rows share a timestamp, and `auto_now_add` inside one transaction
        # can produce exactly that. Without the tiebreak, `current()` picks
        # arbitrarily between them -- a nondeterminism at the centre of an
        # append-only model, which would surface as a flaky test long before
        # anyone saw it in production.
        ordering = ("-created_at", "-id")
        indexes = [
            # Covers both reads: current() and the history list. The FK's own
            # index is on `user` alone, which still leaves a sort. This runs
            # every time a user logs food on a new day, so it is worth the write
            # cost now rather than a migration later.
            models.Index(fields=["user", "-created_at"], name="targetversion_user_recent"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.calories} kcal from {self.effective_from}"
