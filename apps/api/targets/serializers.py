"""Read and write shapes for `/api/targets/`.

Two serializers, never one with `read_only_fields`. The read shape carries
`source` and `rationale`, which a client must never set: `source` is how
MAC-44's history screen labels a row `MANUAL` or `ONBOARDING`, and a client
that can write it can lie about where a number came from. Sharing one class and
marking fields read-only puts that hole one relaxed entry away, which is the
argument `accounts/serializers.py` already makes for the same split.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from accounts.models import User
from targets import services
from targets.models import TargetVersion

# How far past the server's own date a client's calendar date may sit.
#
# The client sends `effective_from` because the server cannot work out the user's
# today: `User.timezone` is "UTC" for everyone until MAC-48 lands, and doc 02
# already has the client send its own `local_date` for `DailyLog` for the same
# reason.
#
# So "not in the future" cannot be checked exactly. A device in UTC+14 is
# legitimately a day ahead of the server, and refusing that would break the
# endpoint for New Zealand every afternoon. One day of slack accepts every real
# timezone and still refuses the thing this guard exists for: a date weeks out,
# which `TargetVersionQuerySet.current()` would then return before it applies.
MAX_CLIENT_DATE_SKEW = timedelta(days=1)


class TargetVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TargetVersion
        fields = [
            "id",
            "calories",
            "protein_g",
            "fiber_g",
            "source",
            "rationale",
            "effective_from",
            "created_at",
        ]
        read_only_fields = fields


class TargetVersionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TargetVersion
        fields = ["calories", "protein_g", "fiber_g", "effective_from"]
        extra_kwargs = {
            "effective_from": {"required": True},
        }

    def validate_effective_from(self, value):
        """Refuse a start date the model's own `current()` would mishandle.

        MAC-38 left this to whoever wrote the endpoint, and its docstring names
        this ticket. `current()` returns the most recently *created* row and
        never reads `effective_from`, so those are the same row only while a
        future date is impossible. Accept one and `current()` starts handing back
        targets that have not started, and its name becomes a lie.
        """
        latest_plausible = timezone.now().date() + MAX_CLIENT_DATE_SKEW
        if value > latest_plausible:
            raise serializers.ValidationError(
                "Cannot start in the future. Send the date on the device."
            )
        return value

    def validate(self, attrs):
        """Apply the absolute tier of MAC-39's clamp, and only that tier.

        The two tiers behave differently here on purpose. Outside the *suggested*
        range the value is stored exactly as typed: a person is allowed to
        disagree with the app about their own body, and MAC-50's screen shows the
        warning. Outside the *absolute* range the write is refused, because
        silently storing a different number than the one someone typed is worse
        than telling them no.

        Only model output gets clamped, and no model output reaches this
        endpoint.

        **`user.current_weight_lb` is optional and may be absent**, because doc
        26 makes exiting onboarding early a supported end state: a user can reach
        Settings having answered nothing. `reject_outside_absolute` then drops
        the protein bound and keeps the calorie and fiber ones, which need no
        weight.

        Refusing the write instead would block the exact person slice 1 exists
        for, whose only route to having targets at all is this endpoint. The cost
        is that they can set a nonsense protein number, which is wrong rather
        than dangerous. Calories are the bound that matters for harm and it
        survives.

        An earlier version gated this on sex *and* weight. The absolute tier
        never reads sex, so that dropped the guard for anyone who answered one
        question and not the other, with the number it needed sitting right
        there.
        """
        user: User = self.context["request"].user
        targets = services.Targets(
            calories=attrs["calories"],
            protein_g=attrs["protein_g"],
            fiber_g=attrs["fiber_g"],
        )
        services.reject_outside_absolute(targets, user.current_weight_lb)
        return attrs

    def create(self, validated_data):
        # Through `services.create_version`, not `TargetVersion.objects.create`.
        # That function also completes onboarding on a user's first target, in
        # the same transaction, and it is the only place that happens. MAC-47
        # exists because the flag had no writer at all, so a second creation
        # path here would recreate the bug it fixed.
        return services.create_version(
            user=self.context["request"].user,
            source=TargetVersion.Source.MANUAL,
            **validated_data,
        )


# The bounds on the six answers, and why each one exists.
#
# These are **data sanity**, not clinical limits. They stop a typo or a hostile
# client before the numbers reach a formula that would happily return nonsense,
# and they are wider than any real user.
#
# The weight band is the exception and it is a hard precondition. Outside 85 to
# 500 lb the suggested calorie floor and ceiling cross and `Range` raises, which
# would be a 500 where a 400 belongs. `services.MINIMUM_SUPPORTED_WEIGHT_LB` and
# its maximum are the source, and `targets/tests/test_units.py` pins the copies
# together.
MINIMUM_AGE = 13
MAXIMUM_AGE = 100
MINIMUM_HEIGHT_IN = 36
MAXIMUM_HEIGHT_IN = 96


class TargetProposalRequestSerializer(serializers.Serializer):
    """The six onboarding answers.

    **Pounds and inches**, the units every screen shows. `services` converts to
    metric once, inside Mifflin-St Jeor, because that formula is the only thing
    in this stack that wants it.

    A plain `Serializer`, not a `ModelSerializer`. None of these six is a column:
    four are transient inputs to a calculation, and the two that are stored
    (`sex`, `current_weight_lb`) belong to `accounts` and are written through a
    different endpoint. A `ModelSerializer` here would imply a model that does
    not exist.
    """

    age = serializers.IntegerField(
        min_value=MINIMUM_AGE,
        max_value=MAXIMUM_AGE,
        help_text=(
            f"Age in years, {MINIMUM_AGE}-{MAXIMUM_AGE}. Mifflin-St Jeor reads it "
            "directly. The bounds are data sanity rather than a policy on who may "
            "use the app."
        ),
    )
    sex = serializers.ChoiceField(
        choices=[(member.value, member.value) for member in services.Sex],
        help_text=(
            "Biological sex, `female` or `male`. Biological rather than gender: it "
            "is the constant term in a formula fitted to body composition. Stored "
            "on the user by `PATCH /api/users/me/`, because editing targets later "
            "needs it."
        ),
    )
    height_in = serializers.IntegerField(
        min_value=MINIMUM_HEIGHT_IN,
        max_value=MAXIMUM_HEIGHT_IN,
        help_text=(
            f"Height in inches, {MINIMUM_HEIGHT_IN}-{MAXIMUM_HEIGHT_IN}. One number, "
            "not feet plus inches: the client shows `5'11\"` and sends 71."
        ),
    )
    weight_lb = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=services.MINIMUM_SUPPORTED_WEIGHT_LB,
        max_value=services.MAXIMUM_SUPPORTED_WEIGHT_LB,
        help_text=(
            f"Body weight in pounds, {services.MINIMUM_SUPPORTED_WEIGHT_LB}-"
            f"{services.MAXIMUM_SUPPORTED_WEIGHT_LB}. **A hard precondition, not a "
            "sanity check.** Outside this band the suggested calorie floor and "
            "ceiling cross and the range inverts."
        ),
    )
    goal = serializers.ChoiceField(
        choices=[(member.value, member.value) for member in services.Goal],
        help_text=(
            "`cut`, `maintain`, or `gain`. Moves calories by a percentage of "
            "maintenance rather than a fixed number, and picks the protein figure."
        ),
    )
    activity = serializers.ChoiceField(
        choices=[(member.value, member.value) for member in services.Activity],
        help_text=(
            "Movement outside deliberate training: `sedentary`, `light`, "
            "`moderate`, or `very_active`. A desk job is sedentary even for "
            "someone who trains hard, which is the most common way people "
            "overstate their burn."
        ),
    )

    def to_answers(self) -> services.Answers:
        """Validated input as the shape `services` works in."""
        data = self.validated_data
        return services.Answers(
            age=data["age"],
            sex=services.Sex(data["sex"]),
            height_in=data["height_in"],
            weight_lb=data["weight_lb"],
            goal=services.Goal(data["goal"]),
            activity=services.Activity(data["activity"]),
        )


class TargetsSerializer(serializers.Serializer):
    """Three numbers, with no identity of their own."""

    calories = serializers.IntegerField(read_only=True)
    protein_g = serializers.IntegerField(read_only=True)
    fiber_g = serializers.IntegerField(read_only=True)


class TargetProposalSerializer(serializers.Serializer):
    """What the formula produced, what it was held to, and why.

    `baseline` is kept beside `targets` so doc 15's result screen can show
    `BASELINE 2180 -> SET 2150`. The two are equal for almost everyone, and the
    screen shows the line only when they differ.

    Nothing is persisted. The user accepts a proposal by posting it to
    `/api/targets/`, which is where a `TargetVersion` gets created.
    """

    targets = TargetsSerializer(read_only=True)
    baseline = TargetsSerializer(
        read_only=True,
        help_text=(
            "What the formula produced before the guardrails saw it. Equal to "
            "`targets` unless `clamped` is true."
        ),
    )
    clamped = serializers.BooleanField(
        read_only=True,
        help_text=(
            "Whether a guardrail moved any of the three numbers. Show the "
            "baseline beside the target when true, and nothing when false."
        ),
    )
    rationale = serializers.CharField(
        read_only=True,
        help_text=(
            "Around 60 words explaining the numbers, for WHY THESE NUMBERS on "
            "screen 9f. Written from a template rather than by a model, so every "
            "figure in it is one of the numbers returned beside it."
        ),
    )
