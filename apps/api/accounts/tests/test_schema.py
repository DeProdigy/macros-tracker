"""Tests for the emitted OpenAPI document.

The first schema test in the project, and it exists for one reason: this app is
the only place that overrides a drf-spectacular default, and the override hooks a
private method.

`RequestBodyOnDeleteAutoSchema._get_request_body` shadows an underscore-prefixed
method. If drf-spectacular renames it or changes its signature, the override
stops being called and nothing raises. `openapi.json` loses the sign-out
`requestBody`, Orval regenerates `deleteCurrentSession()` with no argument, and
the mobile client cannot sign out.

CI's `api-client-drift` job does catch that, but only as "the committed client
differs from the generated one" -- the same red it shows for any legitimate API
change. Whoever sees it on an unrelated dependency bump has to work backwards to
this file from a diff in generated TypeScript. These tests name the intent
instead.
"""

import pytest
from drf_spectacular.generators import SchemaGenerator

SIGN_OUT = "/api/auth/sessions/current/"


@pytest.fixture(scope="module")
def schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


def test_sign_out_carries_a_request_body(schema):
    """The whole point of accounts/schema.py.

    drf-spectacular emits no request body for DELETE by default, so without the
    override this key is simply absent and the generated client takes no
    argument.
    """
    operation = schema["paths"][SIGN_OUT]["delete"]

    assert "requestBody" in operation


def test_the_sign_out_body_is_the_refresh_token(schema):
    """Not just present, but the right shape.

    An override that emitted an empty or wrong component would satisfy the test
    above and still ship a client that cannot sign out.
    """
    content = schema["paths"][SIGN_OUT]["delete"]["requestBody"]["content"]
    ref = content["application/json"]["schema"]["$ref"]
    component = ref.rsplit("/", 1)[-1]

    assert "refresh" in schema["components"]["schemas"][component]["properties"]


def test_the_override_is_scoped_to_sign_out(schema):
    """No other DELETE grows a body by accident.

    The class is applied per-view rather than as DEFAULT_SCHEMA_CLASS precisely
    so that the next DELETE has to make the argument again. This fails if
    somebody promotes it to a global default.
    """
    other_deletes = [
        (path, operations["delete"])
        for path, operations in schema["paths"].items()
        if "delete" in operations and path != SIGN_OUT
    ]

    assert [path for path, operation in other_deletes if "requestBody" in operation] == []
