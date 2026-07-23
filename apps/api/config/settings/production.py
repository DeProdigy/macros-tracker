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

# HSTS is sticky and hard to roll back (browsers cache it; preload is a pain to
# undo; includeSubDomains forces HTTPS on every subdomain). So it ships OFF and
# is ramped up deliberately via env: short max-age → confirm → raise to a year →
# only then includeSubDomains → preload.
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)
