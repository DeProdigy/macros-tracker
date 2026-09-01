from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User

from .constants import ROLLING_WINDOW
from .exceptions import FoodAnalysisQuotaExceeded
from .models import FoodAnalysisCall
from .provider import analyze_food


@dataclass(frozen=True)
class FoodAnalysisRequestSnapshot:
    photo_key: str
    description: str

    def __post_init__(self) -> None:
        if not self.photo_key or "://" in self.photo_key:
            raise ValueError("photo_key must be a stable R2 object key, not a URL.")

    def as_json(self) -> dict[str, str]:
        return {"photo_key": self.photo_key, "description": self.description}


def _now(value: datetime | None) -> datetime:
    return value if value is not None else timezone.now()


def _occupying_calls(*, user: User, at: datetime) -> QuerySet[FoodAnalysisCall]:
    paid_cutoff = at - ROLLING_WINDOW
    reservation_cutoff = at - timedelta(seconds=settings.FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS)
    return FoodAnalysisCall.objects.filter(user=user).filter(
        Q(quota_debited_at__gte=paid_cutoff)
        | Q(
            status=FoodAnalysisCall.Status.RESERVED,
            started_at__gt=reservation_cutoff,
        )
    )


def rolling_usage(*, user: User, at: datetime | None = None) -> int:
    return _occupying_calls(user=user, at=_now(at)).count()


def _retry_at(
    *, occupying: QuerySet[FoodAnalysisCall], at: datetime, used: int, limit: int
) -> datetime:
    timeout = timedelta(seconds=settings.FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS)
    releases = []
    for call in occupying.only("quota_debited_at", "started_at"):
        if call.quota_debited_at is not None:
            releases.append(call.quota_debited_at + ROLLING_WINDOW)
        else:
            releases.append(call.started_at + timeout)
    releases.sort()
    release_index = used - limit
    return releases[release_index] if release_index < len(releases) else at


@transaction.atomic
def reserve_food_analysis_call(
    *, user: User, request: FoodAnalysisRequestSnapshot, at: datetime | None = None
) -> FoodAnalysisCall:
    now = _now(at)
    # The user is the stable lock even when no call rows exist yet. Locking a
    # filtered call queryset would protect nothing for the user's first call.
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    occupying = _occupying_calls(user=locked_user, at=now)
    used = occupying.count()
    limit = settings.FOOD_ANALYSIS_ROLLING_CALL_LIMIT
    if used >= limit:
        raise FoodAnalysisQuotaExceeded(
            limit=limit,
            used=used,
            retry_at=_retry_at(occupying=occupying, at=now, used=used, limit=limit),
        )
    return FoodAnalysisCall.objects.create(
        user=locked_user,
        status=FoodAnalysisCall.Status.RESERVED,
        started_at=now,
        request_payload=request.as_json(),
    )


@transaction.atomic
def mark_provider_called(
    call: FoodAnalysisCall,
    *,
    provider: str,
    model: str,
    at: datetime | None = None,
) -> FoodAnalysisCall:
    now = _now(at)
    User.objects.select_for_update().get(pk=call.user_id)
    locked_call = FoodAnalysisCall.objects.select_for_update().get(pk=call.pk)
    if locked_call.status != FoodAnalysisCall.Status.RESERVED:
        raise ValueError("Only a reserved food-analysis call can be dispatched.")
    if locked_call.provider_called_at is not None:
        raise ValueError("The food-analysis call was already dispatched.")
    reservation_cutoff = now - timedelta(seconds=settings.FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS)
    if locked_call.started_at <= reservation_cutoff:
        raise ValueError("The food-analysis reservation expired before provider dispatch.")
    locked_call.provider = provider
    locked_call.model = model
    locked_call.provider_called_at = now
    locked_call.save(update_fields=("provider", "model", "provider_called_at"))
    call.provider = provider
    call.model = model
    call.provider_called_at = now
    return call


def _latency_ms(call: FoodAnalysisCall, completed_at: datetime) -> int:
    return max(0, round((completed_at - call.started_at).total_seconds() * 1000))


@transaction.atomic
def succeed_food_analysis_call(
    call: FoodAnalysisCall,
    *,
    response_payload: dict[str, Any] | list[Any] | None,
    raw_response: str = "",
    provider_request_id: str = "",
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    usage: dict[str, Any] | None = None,
    estimated_cost_usd: Decimal | None = None,
    at: datetime | None = None,
) -> FoodAnalysisCall:
    User.objects.select_for_update().get(pk=call.user_id)
    locked_call = FoodAnalysisCall.objects.select_for_update().get(pk=call.pk)
    if (
        locked_call.status != FoodAnalysisCall.Status.RESERVED
        or locked_call.provider_called_at is None
    ):
        raise ValueError("A successful call must have been dispatched to the provider.")
    completed_at = _now(at)
    locked_call.status = FoodAnalysisCall.Status.SUCCEEDED
    locked_call.quota_debited_at = locked_call.provider_called_at
    locked_call.completed_at = completed_at
    locked_call.latency_ms = _latency_ms(locked_call, completed_at)
    locked_call.response_payload = response_payload
    locked_call.raw_response = raw_response
    locked_call.provider_request_id = provider_request_id
    locked_call.input_tokens = input_tokens
    locked_call.output_tokens = output_tokens
    locked_call.usage = usage or {}
    locked_call.estimated_cost_usd = estimated_cost_usd
    locked_call.failure_category = ""
    locked_call.failure_message = ""
    locked_call.save()
    call.refresh_from_db()
    return call


@transaction.atomic
def fail_food_analysis_call(
    call: FoodAnalysisCall,
    *,
    category: str,
    message: str,
    response_payload: dict[str, Any] | list[Any] | None = None,
    raw_response: str = "",
    provider_request_id: str = "",
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    usage: dict[str, Any] | None = None,
    estimated_cost_usd: Decimal | None = None,
    billable: bool = False,
    at: datetime | None = None,
) -> FoodAnalysisCall:
    User.objects.select_for_update().get(pk=call.user_id)
    locked_call = FoodAnalysisCall.objects.select_for_update().get(pk=call.pk)
    if locked_call.status != FoodAnalysisCall.Status.RESERVED:
        raise ValueError("Only a reserved food-analysis call can fail.")
    if billable and locked_call.provider_called_at is None:
        raise ValueError("A billable failure must have been dispatched to the provider.")
    completed_at = _now(at)
    locked_call.status = FoodAnalysisCall.Status.FAILED
    locked_call.quota_debited_at = (
        (locked_call.provider_called_at or completed_at) if billable else None
    )
    locked_call.completed_at = completed_at
    locked_call.latency_ms = _latency_ms(locked_call, completed_at)
    locked_call.response_payload = response_payload
    locked_call.raw_response = raw_response
    locked_call.provider_request_id = provider_request_id
    locked_call.input_tokens = input_tokens
    locked_call.output_tokens = output_tokens
    locked_call.usage = usage or {}
    locked_call.estimated_cost_usd = estimated_cost_usd
    locked_call.failure_category = category
    locked_call.failure_message = message[:500]
    locked_call.save()
    call.refresh_from_db()
    return call


def _estimated_cost(input_tokens: int | None, output_tokens: int | None) -> Decimal:
    million = Decimal("1000000")
    return (
        Decimal(input_tokens or 0) * settings.OPENAI_FOOD_INPUT_USD_PER_MILLION / million
        + Decimal(output_tokens or 0) * settings.OPENAI_FOOD_OUTPUT_USD_PER_MILLION / million
    ).quantize(Decimal("0.000001"))


def create_food_analysis(*, user: User, photo_key: str, description: str) -> dict[str, Any]:
    """Retain an image, call the provider, and return only locally validated output."""
    from uploads.services import presign_download, retain_analysis_object

    from .serializers import FoodAnalysisResultSerializer

    call = reserve_food_analysis_call(
        user=user,
        request=FoodAnalysisRequestSnapshot(photo_key=photo_key, description=description),
    )
    try:
        retained_key = retain_analysis_object(key=photo_key, user_id=user.pk)
    except Exception:
        fail_food_analysis_call(call, category="storage_failure", message="Could not retain image.")
        raise

    call.request_payload = FoodAnalysisRequestSnapshot(
        photo_key=retained_key, description=description
    ).as_json()
    call.save(update_fields=("request_payload",))
    try:
        image_url = presign_download(key=retained_key)
        mark_provider_called(call, provider="openai", model=settings.OPENAI_FOOD_ANALYSIS_MODEL)
    except Exception:
        fail_food_analysis_call(
            call, category="provider_setup_failure", message="Could not prepare provider input."
        )
        raise
    try:
        result = analyze_food(image_url=image_url, description=description)
        candidate = {"analysis_id": call.pk, **result.payload}
        items = candidate["items"]
        candidate.update(
            calories=sum((Decimal(str(item["calories"])) for item in items), Decimal("0")),
            protein_g=sum((Decimal(str(item["protein_g"])) for item in items), Decimal("0")),
            fiber_g=sum((Decimal(str(item["fiber_g"])) for item in items), Decimal("0")),
        )
        serializer = FoodAnalysisResultSerializer(data=candidate)
        serializer.is_valid(raise_exception=True)
    except ValidationError:
        fail_food_analysis_call(
            call,
            category="invalid_model_output",
            message="Provider returned invalid structured output.",
            response_payload=candidate if "candidate" in locals() else None,
            billable=True,
        )
        raise
    except ValueError:
        fail_food_analysis_call(
            call,
            category="invalid_model_output",
            message="Provider returned invalid structured output.",
            billable=True,
        )
        raise
    except Exception:
        fail_food_analysis_call(
            call, category="provider_failure", message="Food analysis provider failed."
        )
        raise

    cost = _estimated_cost(result.input_tokens, result.output_tokens)
    succeed_food_analysis_call(
        call,
        response_payload=serializer.data,
        provider_request_id=result.provider_request_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        usage=result.usage,
        estimated_cost_usd=cost,
    )
    return serializer.data
