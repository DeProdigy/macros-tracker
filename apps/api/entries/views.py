import re
from datetime import date
from typing import cast

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from targets.models import TargetVersion

from .models import DailyLog
from .serializers import DaySerializer, FoodEntrySerializer, ManualEntryCreateSerializer, day_data


class EntryListCreateView(APIView):
    @extend_schema(
        operation_id="createManualEntry",
        summary="Log one food manually",
        tags=["entries"],
        request=ManualEntryCreateSerializer,
        responses={
            201: FoodEntrySerializer,
            400: OpenApiResponse(OpenApiTypes.OBJECT, description="Validation error."),
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ManualEntryCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        entry = serializer.save()
        return Response(FoodEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


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
