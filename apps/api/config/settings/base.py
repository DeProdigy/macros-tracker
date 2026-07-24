"""
Base settings shared across all environments.

Values come from the environment via django-environ (see the repo-root
.env.example for the full list). Environment-specific modules — local.py and
production.py — import everything from here and override what differs.
"""

from pathlib import Path

import environ

# config/settings/base.py -> config/settings -> config -> apps/api
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Load apps/api/.env if present. The real .env is gitignored; the committed
# .env.example at the repo root documents every variable.
environ.Env.read_env(BASE_DIR / ".env")


# Security — overridden per environment. The dev fallback here is only ever
# used by local.py; production.py requires a real key from the environment.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-dev-only-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "drf_spectacular",
    # Local apps
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# Database — driven by DATABASE_URL. Locally this points at the Docker Compose
# Postgres; in production, at Railway's managed Postgres.
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://postgres:postgres@localhost:5432/macros_tracker",
    ),
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Custom user model — set before the first migration is ever run.
AUTH_USER_MODEL = "accounts.User"


# Internationalization — everything stored in UTC (see plan doc 02).
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Django REST Framework — sane defaults: authenticated by default, JSON in/out.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # drf-spectacular introspects views/serializers to emit the OpenAPI schema
    # that packages/api-client generates its typed hooks from.
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# OpenAPI schema generation (drf-spectacular).
#
# The emitted schema is the contract the mobile client is generated from, so
# these settings are chosen for generator-friendliness, not human readability.
SPECTACULAR_SETTINGS = {
    "TITLE": "Macros Tracker API",
    "DESCRIPTION": "Typed contract consumed by apps/mobile via packages/api-client.",
    "VERSION": "0.1.0",
    # Split request and response into separate components. Without this a single
    # schema serves both, which forces every field optional — technically true,
    # but it makes the generated types accept anything and catch nothing.
    "COMPONENT_SPLIT_REQUEST": True,
    # The schema is served from its own endpoint; keep it out of the API surface.
    "SERVE_INCLUDE_SCHEMA": False,
    # Strip the routing prefix so generated hook names aren't prefixed with
    # ApiV1... — operationIds are set explicitly per view via @extend_schema.
    "SCHEMA_PATH_PREFIX": "/api",
    # Deterministic ordering. The generated client is committed, so unstable
    # output would show up as phantom diffs and break the MAC-16 drift check.
    "SORT_OPERATIONS": True,
    "SORT_OPERATION_PARAMETERS": True,
}
