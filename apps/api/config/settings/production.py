"""
Production settings.

Selected by wsgi.py / asgi.py (or DJANGO_SETTINGS_MODULE) when deployed to
Railway. Secrets are REQUIRED here — there are no dev fallbacks, so a missing
env var fails loudly at startup instead of silently running insecurely.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Required — raises ImproperlyConfigured if unset, by design.
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# HTTPS / security hardening. Railway terminates TLS at its proxy, so trust the
# forwarded-proto header to detect the original HTTPS request.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# HSTS — start conservative and raise once you've confirmed HTTPS everywhere.
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
