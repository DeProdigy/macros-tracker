from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from accounts.models import User

from .exceptions import FoodAnalysisQuotaExceeded
from .models import FoodAnalysisCall

ROLLING_WINDOW = timedelta(days=30)


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


def _retry_at(*, occupying: QuerySet[FoodAnalysisCall], at: datetime) -> datetime:
    timeout = timedelta(seconds=settings.FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS)
    releases = []
    for call in occupying.only("quota_debited_at", "started_at"):
        if call.quota_debited_at is not None:
            releases.append(call.quota_debited_at + ROLLING_WINDOW)
        else:
            releases.append(call.started_at + timeout)
    return min(releases, default=at)


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
            retry_at=_retry_at(occupying=occupying, at=now),
        )
    return FoodAnalysisCall.objects.create(
        user=locked_user,
        status=FoodAnalysisCall.Status.RESERVED,
        started_at=now,
        request_payload=request.as_json(),
    )


def mark_provider_called(
    call: FoodAnalysisCall,
    *,
    provider: str,
    model: str,
    at: datetime | None = None,
) -> FoodAnalysisCall:
    if call.status != FoodAnalysisCall.Status.RESERVED:
        raise ValueError("Only a reserved food-analysis call can be dispatched.")
    if call.provider_called_at is not None:
        raise ValueError("The food-analysis call was already dispatched.")
    call.provider = provider
    call.model = model
    call.provider_called_at = _now(at)
    call.save(update_fields=("provider", "model", "provider_called_at"))
    return call


def _latency_ms(call: FoodAnalysisCall, completed_at: datetime) -> int:
    return max(0, round((completed_at - call.started_at).total_seconds() * 1000))


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
    if call.status != FoodAnalysisCall.Status.RESERVED or call.provider_called_at is None:
        raise ValueError("A successful call must have been dispatched to the provider.")
    completed_at = _now(at)
    call.status = FoodAnalysisCall.Status.SUCCEEDED
    call.quota_debited_at = call.provider_called_at or completed_at
    call.completed_at = completed_at
    call.latency_ms = _latency_ms(call, completed_at)
    call.response_payload = response_payload
    call.raw_response = raw_response
    call.provider_request_id = provider_request_id
    call.input_tokens = input_tokens
    call.output_tokens = output_tokens
    call.usage = usage or {}
    call.estimated_cost_usd = estimated_cost_usd
    call.failure_category = ""
    call.failure_message = ""
    call.save()
    return call


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
    if call.status != FoodAnalysisCall.Status.RESERVED:
        raise ValueError("Only a reserved food-analysis call can fail.")
    if billable and call.provider_called_at is None:
        raise ValueError("A billable failure must have been dispatched to the provider.")
    completed_at = _now(at)
    call.status = FoodAnalysisCall.Status.FAILED
    call.quota_debited_at = (call.provider_called_at or completed_at) if billable else None
    call.completed_at = completed_at
    call.latency_ms = _latency_ms(call, completed_at)
    call.response_payload = response_payload
    call.raw_response = raw_response
    call.provider_request_id = provider_request_id
    call.input_tokens = input_tokens
    call.output_tokens = output_tokens
    call.usage = usage or {}
    call.estimated_cost_usd = estimated_cost_usd
    call.failure_category = category
    call.failure_message = message[:500]
    call.save()
    return call
