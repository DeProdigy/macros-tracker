"""Read and write shapes for `/api/targets/`.

Two serializers, never one with `read_only_fields`. The read shape carries
`source` and `ai_rationale`, which a client must never set: `source` is how
MAC-44's history screen labels a row `MANUAL` or `ONBOARDING AI`, and a client
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
            "ai_rationale",
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
