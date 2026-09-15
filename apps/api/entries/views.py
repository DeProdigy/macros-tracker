import re
from datetime import date
from typing import cast

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    PolymorphicProxySerializer,
    extend_schema,
)
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from targets.models import TargetVersion

from . import services
from .models import DailyLog, FoodEntry, FoodItem
from .serializers import (
    DaySerializer,
    EntryCopyCreateSerializer,
    EntryItemConflictSerializer,
    FoodEntrySerializer,
    FoodItemSerializer,
    FoodItemUpdateSerializer,
    FoodItemWriteSerializer,
    LoggedDaySerializer,
    ManualEntryCreateSerializer,
    PhotoEntryCreateSerializer,
    RecentEntryCreateSerializer,
    RecentFoodSerializer,
    day_data,
)


class EntryListCreateView(APIView):
    @extend_schema(
        operation_id="createEntry",
        summary="Log one Manual, Photo, or Recent food entry",
        description=(
            "Creates a new food event. Manual requests provide one item, Photo requests reference "
            "a completed analysis, and Recent requests reference one item from the authenticated "
            "user's history. Recent creation copies that snapshot and never changes the old entry."
        ),
        tags=["entries"],
        request=PolymorphicProxySerializer(
            component_name="EntryCreateRequest",
            serializers=[
                ManualEntryCreateSerializer,
                PhotoEntryCreateSerializer,
                RecentEntryCreateSerializer,
                EntryCopyCreateSerializer,
            ],
            resource_type_field_name=None,
        ),
        responses={
            201: FoodEntrySerializer,
            400: OpenApiResponse(OpenApiTypes.OBJECT, description="Validation error."),
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
        },
        examples=[
            OpenApiExample(
                "Re-log one recent food",
                value={
                    "local_date": "2026-09-15",
                    "timezone": "America/New_York",
                    "eaten_at": "2026-09-15T12:30:00-04:00",
                    "recent_item_id": 42,
                    "quantity": "1.50",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request: Request) -> Response:
        source_fields = [
            field
            for field in ("item", "analysis_id", "recent_item_id", "source_entry_id")
            if field in request.data
        ]
        if len(source_fields) != 1:
            raise ValidationError({"non_field_errors": ["Provide exactly one entry source."]})
        serializer_class: (
            type[ManualEntryCreateSerializer]
            | type[PhotoEntryCreateSerializer]
            | type[RecentEntryCreateSerializer]
            | type[EntryCopyCreateSerializer]
        )
        if "analysis_id" in request.data:
            serializer_class = PhotoEntryCreateSerializer
        elif "recent_item_id" in request.data:
            serializer_class = RecentEntryCreateSerializer
        elif "source_entry_id" in request.data:
            serializer_class = EntryCopyCreateSerializer
        else:
            serializer_class = ManualEntryCreateSerializer
        serializer = serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        entry = serializer.save()
        return Response(FoodEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class EntryDetailView(APIView):
    def _entry(self, request: Request, pk: int) -> FoodEntry:
        try:
            return FoodEntry.objects.prefetch_related("items").get(
                pk=pk, daily_log__user=cast(User, request.user)
            )
        except FoodEntry.DoesNotExist:
            raise NotFound from None

    @extend_schema(
        operation_id="getEntry",
        summary="Read one food entry",
        description="Returns one complete entry from the authenticated user's history.",
        tags=["entries"],
        responses={
            200: FoodEntrySerializer,
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
            404: OpenApiResponse(OpenApiTypes.OBJECT, description="Entry not found."),
        },
        examples=[
            OpenApiExample(
                "Manual entry",
                value={
                    "id": 42,
                    "source": "manual",
                    "description": "Greek yogurt",
                    "eaten_at": "2026-09-15T12:30:00-04:00",
                    "calories": "120.00",
                    "protein_g": "18.00",
                    "fiber_g": "2.00",
                    "photo_url": None,
                    "items": [],
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request: Request, pk: int) -> Response:
        return Response(FoodEntrySerializer(self._entry(request, pk)).data)

    @extend_schema(
        operation_id="deleteEntry",
        summary="Delete one food entry",
        description=(
            "Deletes one owned entry and its items. The service removes an unreferenced retained "
            "photo after the database commit."
        ),
        tags=["entries"],
        responses={
            204: None,
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
            404: OpenApiResponse(OpenApiTypes.OBJECT, description="Entry not found."),
        },
    )
    def delete(self, request: Request, pk: int) -> Response:
        try:
            services.delete_entry(user=cast(User, request.user), entry_id=pk)
        except FoodEntry.DoesNotExist:
            raise NotFound from None
        return Response(status=status.HTTP_204_NO_CONTENT)


class FoodListView(APIView):
    @extend_schema(
        operation_id="getFoods",
        summary="List distinct foods from entry history",
        description=(
            "Returns the authenticated user's previously logged items newest-first. Foods are "
            "distinct by normalized name and portion label, and each result keeps the newest "
            "matching item's per-unit macros. The response contains at most 100 foods. Manual, "
            "Photo, and Recent items all participate."
        ),
        tags=["foods"],
        parameters=[
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                required=False,
                description="Case-insensitive match against food name or portion label.",
                examples=[OpenApiExample("Yogurt", value="yogurt")],
            )
        ],
        responses={
            200: RecentFoodSerializer(many=True),
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
        },
        examples=[
            OpenApiExample(
                "Recent foods",
                value={
                    "id": 42,
                    "name": "Greek yogurt",
                    "portion_label": "1 cup",
                    "calories": "120.00",
                    "protein_g": "18.00",
                    "fiber_g": "2.00",
                },
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request: Request) -> Response:
        foods = services.recent_foods(
            user=cast(User, request.user), search=request.query_params.get("search", "")
        )
        return Response(RecentFoodSerializer(foods, many=True).data)


class EntryItemListCreateView(APIView):
    @extend_schema(
        operation_id="createEntryItem",
        summary="Add an item to a food entry",
        description="Adds one item and recalculates the entry and day totals.",
        tags=["entries"],
        request=FoodItemWriteSerializer,
        responses={
            201: FoodItemSerializer,
            400: OpenApiResponse(OpenApiTypes.OBJECT, description="Validation error."),
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
            404: OpenApiResponse(OpenApiTypes.OBJECT, description="Entry not found."),
        },
    )
    def post(self, request: Request, entry_id: int) -> Response:
        serializer = FoodItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = services.create_entry_item(
                user=cast(User, request.user),
                entry_id=entry_id,
                item=services.EditableItem(**serializer.validated_data),
            )
        except FoodEntry.DoesNotExist:
            raise NotFound from None
        return Response(FoodItemSerializer(item).data, status=status.HTTP_201_CREATED)


class EntryItemDetailView(APIView):
    def _item(self, request: Request, entry_id: int, pk: int) -> FoodItem:
        try:
            return FoodItem.objects.get(
                pk=pk,
                entry_id=entry_id,
                entry__daily_log__user=cast(User, request.user),
            )
        except FoodItem.DoesNotExist:
            raise NotFound from None

    @extend_schema(
        operation_id="updateEntryItem",
        summary="Correct one item in a food entry",
        description="Partially updates one item and recalculates the entry and day totals.",
        tags=["entries"],
        request=FoodItemUpdateSerializer,
        responses={
            200: FoodItemSerializer,
            400: OpenApiResponse(OpenApiTypes.OBJECT, description="Validation error."),
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
            404: OpenApiResponse(OpenApiTypes.OBJECT, description="Entry or item not found."),
        },
    )
    def patch(self, request: Request, entry_id: int, pk: int) -> Response:
        current = self._item(request, entry_id, pk)
        serializer = FoodItemUpdateSerializer(current, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            item = services.update_entry_item(
                user=cast(User, request.user),
                entry_id=entry_id,
                item_id=pk,
                changes=serializer.validated_data,
            )
        except (FoodEntry.DoesNotExist, FoodItem.DoesNotExist):
            raise NotFound from None
        except ValueError as exc:
            raise ValidationError({"non_field_errors": [str(exc)]}) from None
        return Response(FoodItemSerializer(item).data)

    @extend_schema(
        operation_id="deleteEntryItem",
        summary="Remove one item from a food entry",
        description="Removes one item and recalculates totals. An entry must retain one item.",
        tags=["entries"],
        responses={
            204: None,
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
            404: OpenApiResponse(OpenApiTypes.OBJECT, description="Entry or item not found."),
            409: EntryItemConflictSerializer,
        },
    )
    def delete(self, request: Request, entry_id: int, pk: int) -> Response:
        try:
            services.delete_entry_item(user=cast(User, request.user), entry_id=entry_id, item_id=pk)
        except (FoodEntry.DoesNotExist, FoodItem.DoesNotExist):
            raise NotFound from None
        except services.EntryRequiresOneItem:
            return Response(
                {
                    "code": "entry_requires_one_item",
                    "detail": "An entry needs at least one item. Delete the entry instead.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DayDetailView(APIView):
    @extend_schema(
        operation_id="getDay",
        summary="Read one local day",
        tags=["days"],
        parameters=[
            OpenApiParameter(
                "local_date",
                OpenApiTypes.DATE,
                OpenApiParameter.PATH,
                description="The phone's local calendar date, YYYY-MM-DD.",
            )
        ],
        responses={
            200: DaySerializer,
            400: OpenApiResponse(OpenApiTypes.OBJECT, description="Invalid local date."),
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
        },
    )
    def get(self, request: Request, local_date: str) -> Response:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", local_date):
                raise ValueError
            parsed = date.fromisoformat(local_date)
        except ValueError:
            return Response({"local_date": ["Enter a date in YYYY-MM-DD format."]}, status=400)
        day = (
            DailyLog.objects.filter(user=cast(User, request.user), local_date=parsed)
            .select_related("target_version")
            .first()
        )
        effective_target: TargetVersion | None = None
        if day is None:
            effective_target = TargetVersion.objects.effective_on(cast(User, request.user), parsed)
        return Response(DaySerializer(day_data(day, parsed, effective_target)).data)


class DayListView(APIView):
    @extend_schema(
        operation_id="getDays",
        summary="List days that contain entries",
        description=(
            "Returns the authenticated user's local dates with entries in one calendar month. "
            "The month query uses YYYY-MM."
        ),
        tags=["days"],
        parameters=[
            OpenApiParameter(
                "month",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                required=True,
                description="Calendar month in YYYY-MM format.",
                examples=[OpenApiExample("September 2026", value="2026-09")],
            )
        ],
        responses={
            200: LoggedDaySerializer(many=True),
            400: OpenApiResponse(OpenApiTypes.OBJECT, description="Invalid month."),
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
        },
        examples=[
            OpenApiExample(
                "Logged days",
                value={"local_date": "2026-09-15"},
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request: Request) -> Response:
        month = request.query_params.get("month", "")
        try:
            if not re.fullmatch(r"\d{4}-\d{2}", month):
                raise ValueError
            start = date.fromisoformat(f"{month}-01")
            end = (
                date(start.year + 1, 1, 1)
                if start.month == 12
                else date(start.year, start.month + 1, 1)
            )
        except ValueError:
            return Response({"month": ["Enter a month in YYYY-MM format."]}, status=400)
        local_dates = (
            DailyLog.objects.filter(
                user=cast(User, request.user),
                local_date__gte=start,
                local_date__lt=end,
                entries__isnull=False,
            )
            .values_list("local_date", flat=True)
            .distinct()
            .order_by("local_date")
        )
        return Response(
            LoggedDaySerializer([{"local_date": value} for value in local_dates], many=True).data
        )
