from django.conf import settings
from django.db import models


class TargetVersionQuerySet(models.QuerySet["TargetVersion"]):
    def for_user(self, user) -> "TargetVersionQuerySet":
        return self.filter(user=user)

    def current(self, user) -> "TargetVersion | None":
        """The user's most recently created version, or None if they have none.

        **"Most recently created", not "in effect on a given date".** The two are
        the same row only while `effective_from` can never be in the future, and
        nothing here enforces that -- MAC-40's create endpoint has to, by
        rejecting a future date. If that ever changes, this method starts
        returning a version that has not begun applying and its name becomes a
        lie. The honest alternative would be
        `.filter(effective_from__lte=<the caller's local date>).first()`, which
        forces every caller to supply a date. Heavier than anything needs today,
        and the note is here so the trade is visible from this file rather than
        buried in a serializer validator.

        Orders explicitly rather than leaning on `Meta.ordering`. This is a
        queryset method, so it is chainable: `TargetVersion.objects
        .order_by("created_at").current(user)` would otherwise hand back the
        oldest row. No caller does that today, and one line removes the
        possibility entirely.

        A method rather than a stored `is_current` boolean. A boolean would be a
        second source of truth that can disagree with the ordering, and keeping
        it accurate means writing to the previous row on every change -- which
        is the in-place update this whole model exists to avoid.

        Returns None rather than raising. A user with no targets is a supported
        state (they logged a meal and skipped onboarding), not an exception, and
        `.latest()` would force every caller to wrap this in a try block.
        """
        return self.for_user(user).order_by("-created_at", "-id").first()


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

    # `_g` is grams. The suffix comes from doc 02 and matches `FoodItem` in E4,
    # so the two halves of the app measure protein the same way. help_text
    # rather than a rename: it reaches the admin and, once MAC-40 serializes
    # these, the generated OpenAPI schema and the TypeScript client with it.
    calories = models.IntegerField(help_text="Daily calorie target, kcal.")
    protein_g = models.IntegerField(help_text="Daily protein target, in grams.")
    fiber_g = models.IntegerField(help_text="Daily fiber target, in grams.")

    source = models.CharField(max_length=32, choices=Source.choices)

    # The model's explanation, shown to the user under WHY THESE NUMBERS.
    #
    # Blank rather than null, per Django's own guidance on text fields: a
    # nullable CharField gives two ways to spell "empty" and every reader then
    # has to handle both. A manual edit has no rationale and stores "".
    ai_rationale = models.TextField(
        blank=True,
        help_text=(
            "The model's plain-English explanation, shown under WHY THESE NUMBERS "
            "on screen 9f. Around 60 words, naming the deficit, the rate, and why "
            "protein is set per kilo of bodyweight. Empty for a manual edit."
        ),
    )

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
        # two rows share a timestamp, and the database is then free to return
        # either -- a nondeterminism at the centre of an append-only model.
        #
        # Ordinary saves do not collide: `auto_now_add` reads Python's clock per
        # row, so two creates land microseconds apart even inside one
        # transaction. Equal timestamps come from `bulk_create`, a data
        # migration, a fixture that sets the column, or an `update()`. That is
        # why the test has to force the collision, and why an earlier version of
        # it passed with the tiebreak removed.
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
