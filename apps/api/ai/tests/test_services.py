import copy
import pickle
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.utils import timezone

from ai.exceptions import FoodAnalysisQuotaExceeded
from ai.models import FoodAnalysisCall
from ai.services import (
    FoodAnalysisRequestSnapshot,
    fail_food_analysis_call,
    mark_provider_called,
    reserve_food_analysis_call,
    rolling_usage,
    succeed_food_analysis_call,
)
from entries.services import ManualItem, create_manual_entry
from targets.models import TargetVersion

User = get_user_model()


def request() -> FoodAnalysisRequestSnapshot:
    return FoodAnalysisRequestSnapshot(
        photo_key="analysis/alex/meal.jpg",
        description="Two eggs and toast",
    )


def test_request_snapshot_refuses_a_presigned_url():
    with pytest.raises(ValueError, match="object key"):
        FoodAnalysisRequestSnapshot(
            photo_key="https://r2.example.test/signed?secret=credential",
            description="meal",
        )


def test_quota_exception_can_cross_process_boundaries():
    error = FoodAnalysisQuotaExceeded(
        limit=500,
        used=500,
        retry_at=timezone.now(),
    )

    assert copy.deepcopy(error) == error
    assert pickle.loads(pickle.dumps(error)) == error


@pytest.fixture
def user(db):
    return User.objects.create_user(email="alex@example.com")


@pytest.mark.django_db
def test_success_records_the_paid_call_and_training_snapshot(user):
    started = timezone.now()
    call = reserve_food_analysis_call(user=user, request=request(), at=started)
    mark_provider_called(
        call, provider="openai", model="food-model", at=started + timedelta(seconds=1)
    )

    succeed_food_analysis_call(
        call,
        response_payload={"items": [{"name": "eggs"}]},
        provider_request_id="req_123",
        input_tokens=120,
        output_tokens=40,
        usage={"input_tokens": 120, "output_tokens": 40},
        estimated_cost_usd=Decimal("0.012345"),
        at=started + timedelta(seconds=2, milliseconds=250),
    )

    call.refresh_from_db()
    assert call.status == FoodAnalysisCall.Status.SUCCEEDED
    assert call.request_payload == {
        "photo_key": "analysis/alex/meal.jpg",
        "description": "Two eggs and toast",
    }
    assert call.response_payload == {"items": [{"name": "eggs"}]}
    assert call.provider == "openai"
    assert call.model == "food-model"
    assert call.provider_request_id == "req_123"
    assert call.input_tokens == 120
    assert call.output_tokens == 40
    assert call.estimated_cost_usd == Decimal("0.012345")
    assert call.latency_ms == 2250
    assert call.quota_debited_at == call.provider_called_at
    assert rolling_usage(user=user, at=started + timedelta(seconds=3)) == 1


@pytest.mark.django_db
def test_billable_provider_failure_records_usage_and_consumes_quota(user):
    started = timezone.now()
    call = reserve_food_analysis_call(user=user, request=request(), at=started)
    mark_provider_called(call, provider="openai", model="food-model", at=started)

    fail_food_analysis_call(
        call,
        category="invalid_model_output",
        message="Provider returned invalid structured output",
        raw_response="not-json",
        input_tokens=80,
        output_tokens=5,
        estimated_cost_usd=Decimal("0.001000"),
        billable=True,
        at=started + timedelta(seconds=1),
    )

    call.refresh_from_db()
    assert call.status == FoodAnalysisCall.Status.FAILED
    assert call.raw_response == "not-json"
    assert call.failure_category == "invalid_model_output"
    assert call.quota_debited_at == call.provider_called_at
    assert rolling_usage(user=user, at=started + timedelta(seconds=2)) == 1


@pytest.mark.django_db
def test_local_failure_is_a_record_but_does_not_consume_paid_quota(user):
    started = timezone.now()
    call = reserve_food_analysis_call(user=user, request=request(), at=started)

    fail_food_analysis_call(
        call,
        category="invalid_photo_key",
        message="The pending object no longer exists",
        at=started + timedelta(seconds=1),
    )

    call.refresh_from_db()
    assert call.status == FoodAnalysisCall.Status.FAILED
    assert call.provider_called_at is None
    assert call.quota_debited_at is None
    assert rolling_usage(user=user, at=started + timedelta(seconds=2)) == 0


@pytest.mark.django_db
def test_a_call_cannot_be_marked_paid_without_provider_dispatch(user):
    call = reserve_food_analysis_call(user=user, request=request())

    with pytest.raises(ValueError, match="must have been dispatched"):
        succeed_food_analysis_call(call, response_payload={})
    with pytest.raises(ValueError, match="billable failure"):
        fail_food_analysis_call(call, category="network", message="failed", billable=True)


@pytest.mark.django_db
def test_stale_retry_cannot_overwrite_a_finalized_call(user):
    call = reserve_food_analysis_call(user=user, request=request())
    mark_provider_called(call, provider="openai", model="food-model")
    stale_retry = FoodAnalysisCall.objects.get(pk=call.pk)

    succeed_food_analysis_call(call, response_payload={"items": []})

    with pytest.raises(ValueError, match="Only a reserved food-analysis call can fail"):
        fail_food_analysis_call(
            stale_retry,
            category="late_retry",
            message="A retried finalizer arrived after success.",
            billable=True,
        )

    call.refresh_from_db()
    assert call.status == FoodAnalysisCall.Status.SUCCEEDED
    assert call.failure_category == ""


@pytest.mark.django_db
def test_only_the_previous_30_days_count(user):
    now = timezone.now()
    calls = [
        FoodAnalysisCall(
            user=user,
            status=FoodAnalysisCall.Status.SUCCEEDED,
            started_at=now - timedelta(days=31),
            provider_called_at=now - timedelta(days=30),
            quota_debited_at=now - timedelta(days=30),
        ),
        FoodAnalysisCall(
            user=user,
            status=FoodAnalysisCall.Status.SUCCEEDED,
            started_at=now - timedelta(days=31),
            provider_called_at=now - timedelta(days=30, microseconds=1),
            quota_debited_at=now - timedelta(days=30, microseconds=1),
        ),
    ]
    FoodAnalysisCall.objects.bulk_create(calls)

    assert rolling_usage(user=user, at=now) == 1


@pytest.mark.django_db
def test_live_reservation_occupies_capacity_but_expired_one_does_not(user, settings):
    settings.FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS = 300
    now = timezone.now()
    FoodAnalysisCall.objects.bulk_create(
        [
            FoodAnalysisCall(
                user=user,
                status=FoodAnalysisCall.Status.RESERVED,
                started_at=now - timedelta(seconds=299),
            ),
            FoodAnalysisCall(
                user=user,
                status=FoodAnalysisCall.Status.RESERVED,
                started_at=now - timedelta(seconds=300),
            ),
        ]
    )

    assert rolling_usage(user=user, at=now) == 1


@pytest.mark.django_db
def test_boundary_rejection_is_typed_and_creates_no_extra_row(user, settings):
    settings.FOOD_ANALYSIS_ROLLING_CALL_LIMIT = 2
    now = timezone.now()
    for offset in (timedelta(days=2), timedelta(days=1)):
        FoodAnalysisCall.objects.create(
            user=user,
            status=FoodAnalysisCall.Status.SUCCEEDED,
            started_at=now - offset,
            provider_called_at=now - offset,
            quota_debited_at=now - offset,
        )

    with pytest.raises(FoodAnalysisQuotaExceeded) as caught:
        reserve_food_analysis_call(user=user, request=request(), at=now)

    assert caught.value.code == "food_analysis_quota_exceeded"
    assert caught.value.limit == 2
    assert caught.value.used == 2
    assert caught.value.window_days == 30
    assert caught.value.retry_at == now - timedelta(days=2) + timedelta(days=30)
    assert FoodAnalysisCall.objects.filter(user=user).count() == 2


@pytest.mark.django_db
def test_retry_time_frees_enough_slots_after_limit_is_lowered(user, settings):
    settings.FOOD_ANALYSIS_ROLLING_CALL_LIMIT = 1
    now = timezone.now()
    debit_times = [now - timedelta(days=3), now - timedelta(days=2), now - timedelta(days=1)]
    for debited_at in debit_times:
        FoodAnalysisCall.objects.create(
            user=user,
            status=FoodAnalysisCall.Status.SUCCEEDED,
            started_at=debited_at,
            provider_called_at=debited_at,
            quota_debited_at=debited_at,
        )

    with pytest.raises(FoodAnalysisQuotaExceeded) as caught:
        reserve_food_analysis_call(user=user, request=request(), at=now)

    assert caught.value.used == 3
    assert caught.value.retry_at == debit_times[-1] + timedelta(days=30)


@pytest.mark.django_db
def test_expired_reservation_cannot_dispatch_after_capacity_is_reused(user, settings):
    settings.FOOD_ANALYSIS_ROLLING_CALL_LIMIT = 1
    settings.FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS = 300
    started = timezone.now()
    expired = reserve_food_analysis_call(user=user, request=request(), at=started)
    replacement = reserve_food_analysis_call(
        user=user,
        request=request(),
        at=started + timedelta(seconds=301),
    )

    with pytest.raises(ValueError, match="expired before provider dispatch"):
        mark_provider_called(
            expired,
            provider="openai",
            model="food-model",
            at=started + timedelta(seconds=301),
        )

    mark_provider_called(
        replacement,
        provider="openai",
        model="food-model",
        at=started + timedelta(seconds=301),
    )


@pytest.mark.django_db
def test_quotas_are_per_user(user, settings):
    settings.FOOD_ANALYSIS_ROLLING_CALL_LIMIT = 1
    other = User.objects.create_user(email="other@example.com")
    now = timezone.now()
    paid = reserve_food_analysis_call(user=user, request=request(), at=now)
    mark_provider_called(paid, provider="openai", model="food-model", at=now)
    succeed_food_analysis_call(paid, response_payload={}, at=now)

    assert reserve_food_analysis_call(user=other, request=request(), at=now).user == other


@pytest.mark.django_db
def test_account_deletion_removes_sensitive_snapshots(user):
    reserve_food_analysis_call(user=user, request=request())

    user.delete()

    assert FoodAnalysisCall.objects.count() == 0


@pytest.mark.django_db
def test_manual_logging_creates_no_ai_call(user):
    today = timezone.now().date()
    TargetVersion.objects.create(
        user=user,
        calories=2000,
        protein_g=150,
        fiber_g=30,
        source=TargetVersion.Source.MANUAL,
        effective_from=today,
    )
    create_manual_entry(
        user=user,
        local_date=today,
        eaten_at=timezone.now(),
        item=ManualItem(
            name="Toast",
            quantity=Decimal("1.00"),
            calories=Decimal("100.00"),
            protein_g=Decimal("3.00"),
            fiber_g=Decimal("2.00"),
        ),
    )

    assert FoodAnalysisCall.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_requests_cannot_both_take_the_last_slot(settings):
    settings.FOOD_ANALYSIS_ROLLING_CALL_LIMIT = 1
    user = User.objects.create_user(email="race@example.com")
    user_id = user.pk
    now = timezone.now()

    def reserve():
        close_old_connections()
        try:
            thread_user = User.objects.get(pk=user_id)
            call = reserve_food_analysis_call(user=thread_user, request=request(), at=now)
            return ("reserved", call.pk)
        except FoodAnalysisQuotaExceeded:
            return ("rejected", None)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve(), range(2)))

    assert sorted(result[0] for result in results) == ["rejected", "reserved"]
    assert FoodAnalysisCall.objects.filter(user_id=user_id).count() == 1
