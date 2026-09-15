import re
from datetime import date
from typing import cast

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
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
    EntryItemConflictSerializer,
    FoodEntrySerializer,
    FoodItemSerializer,
    FoodItemUpdateSerializer,
    FoodItemWriteSerializer,
    ManualEntryCreateSerializer,
    PhotoEntryCreateSerializer,
    day_data,
)


class EntryListCreateView(APIView):
    @extend_schema(
        operation_id="createEntry",
        summary="Log one Manual or Photo food entry",
        tags=["entries"],
        request=PolymorphicProxySerializer(
            component_name="EntryCreateRequest",
            serializers=[ManualEntryCreateSerializer, PhotoEntryCreateSerializer],
            resource_type_field_name=None,
        ),
        responses={
            201: FoodEntrySerializer,
            400: OpenApiResponse(OpenApiTypes.OBJECT, description="Validation error."),
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
        },
    )
    def post(self, request: Request) -> Response:
        serializer_class = (
            PhotoEntryCreateSerializer
            if "analysis_id" in request.data
            else ManualEntryCreateSerializer
        )
        serializer = serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        entry = serializer.save()
        return Response(FoodEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


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
