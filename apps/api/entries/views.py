from datetime import date
from typing import cast

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import DailyLog
from .serializers import DaySerializer, FoodEntrySerializer, ManualEntryCreateSerializer, day_data


class EntryListCreateView(APIView):
    @extend_schema(
        operation_id="createManualEntry",
        tags=["entries"],
        request=ManualEntryCreateSerializer,
        responses={201: FoodEntrySerializer, 400: None, 401: None},
    )
    def post(self, request: Request) -> Response:
        serializer = ManualEntryCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        entry = serializer.save()
        return Response(FoodEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class DayDetailView(APIView):
    @extend_schema(
        operation_id="getDay",
        tags=["days"],
        responses={200: DaySerializer, 400: None, 401: None},
    )
    def get(self, request: Request, local_date: str) -> Response:
        try:
            parsed = date.fromisoformat(local_date)
        except ValueError:
            return Response({"local_date": ["Enter a date in YYYY-MM-DD format."]}, status=400)
        day = (
            DailyLog.objects.filter(user=cast(User, request.user), local_date=parsed)
            .select_related("target_version")
            .first()
        )
        return Response(DaySerializer(day_data(day, parsed)).data)
