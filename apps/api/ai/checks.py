from django.conf import settings
from django.core.checks import Error, register


@register()
def check_food_analysis_quota_settings(app_configs, **kwargs):
    errors = []
    if settings.FOOD_ANALYSIS_ROLLING_CALL_LIMIT <= 0:
        errors.append(Error("FOOD_ANALYSIS_ROLLING_CALL_LIMIT must be positive.", id="ai.E001"))
    if settings.FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS <= 0:
        errors.append(
            Error(
                "FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS must be positive.",
                id="ai.E002",
            )
        )
    return errors
