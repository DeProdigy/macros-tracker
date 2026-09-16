from dataclasses import dataclass
from typing import Any

from django.conf import settings
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field


# This model is the wire format OpenAI must generate, not the shape this app
# stores. Note the comment, not a docstring: pydantic copies a class docstring
# into the schema's `description`, and the SDK sends the schema on every call.
# Engineering notes there would be billed as input tokens and read by the model
# as instructions.
#
# The macros are `float` and not `Decimal` on purpose. Pydantic renders a
# `Decimal` field as `anyOf: [number, string-with-pattern]`, and that pattern
# holds a negative lookahead. OpenAI compiles this schema into a decoder grammar
# before it generates anything, and it cannot compile that shape. The call then
# returns `status=incomplete` with `reason=max_output_tokens` and zero tokens
# used, which points at a budget that was never the problem.
#
# Precision is not lost. `_rounded_macro` in services.py converts each value
# with `Decimal(str(value))` before it rounds and sums, and `str()` on a float
# returns the shortest string that round-trips.
#
# The wrong choice: reach for `Decimal` here because the database column is a
# decimal. A provider schema is bound by what a third party can generate, not by
# how this app stores the result.
class ProviderFoodItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    portion: str = Field(min_length=1, max_length=100)
    calories: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    fiber_g: float = Field(ge=0)


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


@dataclass(frozen=True)
class ProviderOutputError(Exception):
    payload: dict[str, Any]
    raw_response: str
    provider_request_id: str
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
        reasoning={"effort": "minimal"},
        max_output_tokens=4096,
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
    usage_obj = response.usage
    usage = usage_obj.model_dump(mode="json") if usage_obj is not None else {}
    if parsed is None:
        raise ProviderOutputError(
            payload={
                "status": response.status,
                "incomplete_details": (
                    response.incomplete_details.model_dump(mode="json")
                    if response.incomplete_details is not None
                    else None
                ),
                "output": [item.model_dump(mode="json") for item in response.output],
            },
            raw_response=response.output_text,
            provider_request_id=response.id,
            input_tokens=getattr(usage_obj, "input_tokens", None),
            output_tokens=getattr(usage_obj, "output_tokens", None),
            usage=usage,
        )
    return ProviderResult(
        payload=parsed.model_dump(mode="json"),
        provider_request_id=response.id,
        model=response.model,
        input_tokens=getattr(usage_obj, "input_tokens", None),
        output_tokens=getattr(usage_obj, "output_tokens", None),
        usage=usage,
    )
