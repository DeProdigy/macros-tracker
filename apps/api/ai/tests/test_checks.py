from django.core import checks


def test_call_limit_must_be_positive(settings):
    settings.FOOD_ANALYSIS_ROLLING_CALL_LIMIT = 0

    errors = checks.run_checks()

    assert any(error.id == "ai.E001" for error in errors)


def test_reservation_timeout_must_be_positive(settings):
    settings.FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS = 0

    errors = checks.run_checks()

    assert any(error.id == "ai.E002" for error in errors)
