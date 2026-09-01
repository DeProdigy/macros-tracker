import pytest
from drf_spectacular.generators import SchemaGenerator


@pytest.fixture(scope="module")
def schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


def test_entry_create_request_body_is_required(schema: dict):
    request_body = schema["paths"]["/api/entries/"]["post"]["requestBody"]

    assert request_body["required"] is True


def test_food_entry_photo_url_is_nullable(schema: dict):
    photo_url = schema["components"]["schemas"]["FoodEntry"]["properties"]["photo_url"]

    assert photo_url["nullable"] is True
