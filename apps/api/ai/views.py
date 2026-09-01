import logging
from typing import cast

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .exceptions import FoodAnalysisQuotaExceeded
from .serializers import (
    FoodAnalysisErrorSerializer,
    FoodAnalysisQuotaErrorSerializer,
    FoodAnalysisRequestSerializer,
    FoodAnalysisResultSerializer,
)
from .services import create_food_analysis

logger = logging.getLogger(__name__)


class FoodAnalysisCreateView(APIView):
    @extend_schema(
        operation_id="createFoodAnalysis",
        summary="Create an itemized food analysis",
        description=(
            "Retains one uploaded meal photo and creates a validated itemized estimate. "
            "The request consumes rolling quota only after paid provider work."
        ),
        tags=["analyses"],
        request=FoodAnalysisRequestSerializer,
        responses={
            201: FoodAnalysisResultSerializer,
            400: OpenApiResponse(OpenApiTypes.OBJECT, description="Validation error."),
            401: OpenApiResponse(OpenApiTypes.OBJECT, description="Authentication error."),
            429: FoodAnalysisQuotaErrorSerializer,
            502: FoodAnalysisErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = FoodAnalysisRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data["photo_key"].startswith(f"pending/{request.user.pk}/"):
            return Response(
                {"photo_key": ["Not a pending upload belonging to this user."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = create_food_analysis(
                user=cast(User, request.user), **serializer.validated_data
            )
        except FoodAnalysisQuotaExceeded as exc:
            payload = {
                "detail": str(exc),
                "limit": exc.limit,
                "used": exc.used,
                "retry_at": exc.retry_at,
            }
            return Response(
                FoodAnalysisQuotaErrorSerializer(payload).data,
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except ValidationError:
            return Response(
                {"code": "food_analysis_invalid_output", "detail": "Try another photo."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception("Food analysis failed.")
            return Response(
                {"code": "food_analysis_failed", "detail": "Could not analyze this photo."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(result, status=status.HTTP_201_CREATED)
