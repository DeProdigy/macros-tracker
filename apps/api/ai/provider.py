from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.conf import settings
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field


class ProviderFoodItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    portion: str = Field(min_length=1, max_length=100)
    calories: Decimal = Field(ge=0)
    protein_g: Decimal = Field(ge=0)
    fiber_g: Decimal = Field(ge=0)


class ProviderFoodAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProviderFoodItem] = Field(min_length=1, max_length=30)


@dataclass(frozen=True)
class ProviderResult:
    payload: dict[str, Any]
    provider_request_id: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    usage: dict[str, Any]


def analyze_food(*, image_url: str, description: str) -> ProviderResult:
    """Call OpenAI through one replaceable provider boundary."""
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    description_text = description or "No description was supplied. Use only visible evidence."
    response = client.responses.parse(
        model=settings.OPENAI_FOOD_ANALYSIS_MODEL,
        store=False,
        input=[
            {
                "role": "system",
                "content": (
                    "Estimate every distinct food visible in this meal photo. The user's "
                    "description is strong evidence and resolves ambiguity. Return practical "
                    "portion labels and calories, protein grams, and fiber grams for each item."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"User description: {description_text}"},
                    {"type": "input_image", "image_url": image_url, "detail": "high"},
                ],
            },
        ],
        text_format=ProviderFoodAnalysis,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise ValueError("The provider returned no structured food analysis.")
    usage_obj = response.usage
    usage = usage_obj.model_dump(mode="json") if usage_obj is not None else {}
    return ProviderResult(
        payload=parsed.model_dump(mode="json"),
        provider_request_id=response.id,
        model=response.model,
        input_tokens=getattr(usage_obj, "input_tokens", None),
        output_tokens=getattr(usage_obj, "output_tokens", None),
        usage=usage,
    )
