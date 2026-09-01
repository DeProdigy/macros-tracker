"""
Production settings.

Selected by wsgi.py / asgi.py (or DJANGO_SETTINGS_MODULE) when deployed to
Railway. Secrets are REQUIRED here — there are no dev fallbacks, so a missing
env var fails loudly at startup instead of silently running insecurely.
"""

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, env

DEBUG = False

# Required — raises ImproperlyConfigured if unset, by design.
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
OPENAI_API_KEY = env("OPENAI_API_KEY")

# Static files.
#
# Only the Django admin and the Swagger UI need assets, so WhiteNoise serving
# them from the app process is sufficient — no CDN or bucket for a handful of
# CSS files. Both settings below live here rather than in base.py because
# neither is wanted outside production:
#
#   * The middleware is redundant under DEBUG=True (Django serves static files
#     itself) and warns on every request that STATIC_ROOT does not exist.
#   * The Manifest storage raises for any asset missing from the manifest —
#     good in production, but Django forces DEBUG=False under pytest, so in
#     base.py it would break every test rendering {% static %} in CI, where
#     collectstatic never runs.
#
# Inserted directly after SecurityMiddleware rather than appended: WhiteNoise
# must short-circuit static requests before CommonMiddleware, sessions, or auth
# do any work on them, and appending would put it last. The position is looked
# up instead of hardcoded so reordering base.py's list can't silently move it.
_SECURITY_MIDDLEWARE = "django.middleware.security.SecurityMiddleware"
_whitenoise_position = MIDDLEWARE.index(_SECURITY_MIDDLEWARE) + 1
MIDDLEWARE = [
    *MIDDLEWARE[:_whitenoise_position],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[_whitenoise_position:],
]

# `collectstatic` runs in the image build — see apps/api/Dockerfile.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# HTTPS / security hardening. Railway terminates TLS at its proxy, so trust the
# forwarded-proto header to detect the original HTTPS request.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

# Railway's health check probes the container directly on the internal network,
# over plain HTTP and without the X-Forwarded-Proto header the redirect logic
# above depends on. Without this exemption every probe gets a 301, the platform
# reads that as failing, and the deploy never goes live — while the app is in
# fact perfectly healthy. The pattern is matched against request.path with the
# leading slash stripped, and is anchored so it exempts nothing else.
SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]
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

# The last two rungs of that ramp, silenced because deferring them is the
# decision above rather than an oversight:
#
#   W005  SECURE_HSTS_INCLUDE_SUBDOMAINS is not True
#   W021  SECURE_HSTS_PRELOAD is not True
#
# Both are irreversible in practice — includeSubDomains breaks any subdomain not
# yet on HTTPS, and preload removal takes months to propagate through browser
# release cycles. Turning them on before the app owns a stable custom domain
# risks locking out a domain that doesn't exist yet.
#
# They stay silenced only so `check --deploy` reports nothing unexamined; the
# env vars above are what actually enable them, and this list should shrink when
# they do. Note the check surfaced here is conditional: at HSTS_SECONDS=0 Django
# raises W004 instead, and that one is deliberately NOT silenced — it means HSTS
# is off entirely, which is a real finding rather than a deferred one.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
