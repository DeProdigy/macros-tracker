"""
Local / development settings.

Selected by default via manage.py. Safe, permissive defaults for working on
your machine — never used in production.
"""

from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Print emails to the console instead of sending them — no provider account
# needed to develop verification / password-reset flows (plan doc 04).
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Enable DRF's browsable API in the browser while developing.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
