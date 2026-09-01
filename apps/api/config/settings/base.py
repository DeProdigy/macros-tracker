"""
Base settings shared across all environments.

Values come from the environment via django-environ (see the repo-root
.env.example for the full list). Environment-specific modules — local.py and
production.py — import everything from here and override what differs.
"""

from datetime import timedelta
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
    # Stores rotated/blacklisted refresh tokens. Required for
    # BLACKLIST_AFTER_ROTATION below to have anywhere to write.
    "rest_framework_simplejwt.token_blacklist",
    # Local apps
    "accounts",
    "targets",
    "entries",
    "ai",
    "uploads",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # production.py inserts WhiteNoise directly after SecurityMiddleware.
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
#
# This is an API — only the Django admin and the Swagger UI need static assets.
# WhiteNoise serves them straight from the app process, which is why there is no
# CDN or S3 bucket here: the volume is a handful of admin CSS files, and adding
# object storage for that would be cost without benefit.
STATIC_URL = "static/"
# Where `collectstatic` writes. Gitignored and built during the container image
# build, not committed — it's derived output.
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Object storage — Cloudflare R2 (food photos, see plan doc 09).
#
# R2 is S3-compatible, so django-storages' S3 backend drives it; what differs is
# the endpoint and two settings that produce opaque errors when wrong:
#
#   * SIGNATURE_VERSION must be s3v4. R2 rejects earlier signing, and the
#     failure surfaces as a generic auth error rather than "wrong signature
#     version", which sends you looking at your credentials instead.
#   * REGION must be the literal "auto". R2 has no regions; an AWS region name
#     is accepted at signing time and then fails at request time.
#
# The bucket is private and stays private. Nothing is ever served from it
# directly — reads and writes both go through presigned URLs (see uploads/).
R2_ACCOUNT_ID = env("R2_ACCOUNT_ID", default="")
R2_BUCKET_NAME = env("R2_BUCKET_NAME", default="")
R2_ACCESS_KEY_ID = env("R2_ACCESS_KEY_ID", default="")
R2_SECRET_ACCESS_KEY = env("R2_SECRET_ACCESS_KEY", default="")
# Derived from the account ID, but overridable — R2 also issues per-bucket
# endpoints, and tests point this at a local stub.
R2_ENDPOINT_URL = env(
    "R2_ENDPOINT_URL",
    default=(f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else ""),
)

# Presigned URL lifetimes. A presigned URL is a bearer credential: anyone
# holding it has access for its full lifetime, so these are deliberately short.
# Uploads are seconds-of-work and get minutes; reads are rendered in a list view
# that may sit on screen a while, so they get longer but still expire.
R2_UPLOAD_URL_EXPIRY_SECONDS = env.int("R2_UPLOAD_URL_EXPIRY_SECONDS", default=300)
R2_DOWNLOAD_URL_EXPIRY_SECONDS = env.int("R2_DOWNLOAD_URL_EXPIRY_SECONDS", default=3600)

# Upload constraints, enforced before anything is signed. Without a ceiling a
# client can PUT hundreds of megabytes and you pay to store something you never
# wanted; without a type allowlist the bucket accepts anything at all.
R2_MAX_UPLOAD_BYTES = env.int("R2_MAX_UPLOAD_BYTES", default=10 * 1024 * 1024)
# Maps accepted content types to the extension used in the object key. HEIC is
# included because it is the iPhone camera default.
R2_ALLOWED_UPLOAD_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}

# Paid food-analysis safety control (MAC-49).
#
# The rows in `ai.FoodAnalysisCall` are the source of truth. This value is only
# the admission ceiling; there is deliberately no second monthly counter that
# can drift. A reservation occupies a slot briefly while the request crosses
# the provider boundary. If the worker dies before dispatch, the timeout gives
# that capacity back while retaining the audit row.
FOOD_ANALYSIS_ROLLING_CALL_LIMIT = env.int("FOOD_ANALYSIS_ROLLING_CALL_LIMIT", default=500)
FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS = env.int(
    "FOOD_ANALYSIS_RESERVATION_TIMEOUT_SECONDS", default=300
)


# Caching.
#
# Declared explicitly rather than left to Django's implicit default, which is
# this exact backend. The reason it is written down is the consequence: LocMemCache
# is per *process*, so each gunicorn worker keeps its own copy of everything here.
#
# What that costs the Apple JWKS cache in accounts/services.py: with N workers we
# hold N copies of Apple's public keys and N independent refetch cooldown locks,
# so the worst-case fetch rate against Apple is N per cooldown window rather than
# one. Bounded and acceptable at this size. It stops being acceptable the moment
# something here needs to be consistent across workers — a rate limiter, an
# idempotency key, a lock that actually has to be exclusive. That is when this
# becomes Redis, and this comment is the marker for it.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "macros-tracker",
    },
}


# Sign in with Apple.
#
# Only the client ID is read. APPLE_TEAM_ID / APPLE_KEY_ID / APPLE_PRIVATE_KEY
# exist in .env.example for Apple's server-to-server endpoints (token exchange,
# revocation), which the MVP never calls — a native client hands us an identity
# token we verify locally against Apple's public keys.
#
# This is the expected `aud` claim, and it is the check that stops a valid Apple
# identity token minted for somebody else's app from authenticating against this
# API. No default that could pass silently: accounts/services.py raises
# ImproperlyConfigured on an empty value rather than comparing `aud` against "".
APPLE_CLIENT_ID = env("APPLE_CLIENT_ID", default="")


# Django REST Framework — sane defaults: authenticated by default, JSON in/out.
REST_FRAMEWORK = {
    # JWT first: it is how the mobile client authenticates. Session auth stays
    # beneath it so the Swagger UI at /api/docs/ still works against a logged-in
    # admin session.
    #
    # The order also decides the 401 challenge. DRF takes the WWW-Authenticate
    # header from the *first* authenticator, so with JWT leading, an
    # unauthenticated request now gets 401 rather than the 403 SessionAuth
    # produces. That is the correct answer for a bearer-token API.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # Rates for the scoped throttles in accounts/throttles.py. Declared here
    # rather than on the classes because DRF resolves them from settings, which
    # is also what lets a test override one without touching the view.
    #
    # Both apply to the sign-in endpoint and both must pass. See that module for
    # why there are two, and for why the throttle is not the security control.
    "DEFAULT_THROTTLE_RATES": {
        "signin-burst": "10/min",
        "signin-sustained": "60/hour",
        # One device needs ~4 refreshes an hour against a 15-minute access
        # lifetime. 20/min is far above that on purpose: the scope keys on IP,
        # so an office behind one address shares it, and this is the endpoint
        # every signed-in client must reach. Sized to stop a client stuck in a
        # retry loop, which would otherwise run thousands a minute.
        "refresh": "20/min",
        # Arithmetic, no network and no writes, so this is a loop guard rather
        # than a cost guard. A real user answers six questions once and may
        # recompute a few times from Settings; 30/min is far above that and far
        # below what a client retrying on every keystroke would produce.
        "target-proposal": "30/min",
    },
    # How many hops in front of this container append to X-Forwarded-For.
    # `BaseThrottle.get_ident` reads it as `addrs[-min(n, len(addrs))]`, so it
    # counts backwards from the right of the chain. Leaving it unset is not
    # neutral: get_ident then falls to its last line and uses the entire chain
    # as the throttle identity.
    #
    # Measured, not assumed. MAC-36 logged the real chain from the deployed
    # container in Aug 2026 and probed /api/ping/ with 0, 1, 2, and 5 forged
    # left-hand entries. Every probe arrived as exactly two entries,
    # "<caller public IP>, <Railway address>", with the forged ones gone.
    # So Railway replaces the header rather than appending to it, and 2 lands
    # on the caller.
    #
    # Two facts that follow, both easy to get backwards:
    #
    # - The caller cannot forge this identity, because Railway overwrites what
    #   it sends. The bypass this ticket was filed for does not exist. What did
    #   exist is narrower: unset, the identity was the whole chain, and the
    #   right-hand Railway address rotates. 152.233.47.65 through .69 all
    #   appeared inside five minutes, so one caller was spread over several
    #   buckets and got a multiple of the intended allowance.
    # - Setting this too low is the dangerous direction, not too high. 1 would
    #   select the Railway address, which every caller shares, and the sign-in
    #   endpoint would rate-limit the whole world into one bucket.
    #
    # Tied to Railway's topology. A CDN in front of it, or a platform change to
    # how the header is written, invalidates the number. Re-measure the same
    # way rather than adjusting it by reasoning.
    "NUM_PROXIES": 2,
    # drf-spectacular introspects views/serializers to emit the OpenAPI schema
    # that packages/api-client generates its typed hooks from.
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# JSON Web Tokens (djangorestframework-simplejwt).
#
# Lifetimes are hardcoded rather than read from the environment, unlike the R2
# expiries above. A token lifetime is a security decision, not a per-environment
# fact: making it a Railway variable would let production drift to a 90-day
# refresh window with no code review.
#
# Access tokens are deliberately short. Nothing checks a blacklist on the access
# path, so an access token cannot be revoked before it expires -- 15 minutes is
# the window an attacker gets. Going much shorter just means a user returning to
# a backgrounded app eats a refresh round-trip on every launch.
#
# Refresh tokens rotate on every use and the old one is blacklisted, so a stolen
# refresh token stops working as soon as the real client refreshes. Note what
# this does and does not buy: reuse of a rotated token *fails*, but simplejwt
# emits no signal and does not invalidate the token family, so nobody is
# notified. Detection is a follow-up, not something installing this gives us.
#
# SIGNING_KEY defaults to SECRET_KEY, which is left alone. Consequence worth
# knowing before an incident: rotating DJANGO_SECRET_KEY in Railway signs every
# user out at once.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
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
    # Enums are hoisted into shared components named after the *field*, so a
    # bare `status` ChoiceField becomes `StatusEnum` — a name the next
    # serializer with a `status` field would collide with, forcing one of them
    # to be renamed and churning the generated client over an unrelated change.
    # Naming them explicitly keeps the collision from ever arising.
    "ENUM_NAME_OVERRIDES": {
        "HealthStatusEnum": "config.serializers.HEALTH_STATUS_CHOICES",
        # `sex` appears on two request shapes: the user settings PATCH and the
        # target proposal. Without this, spectacular could not name either and
        # emitted `SexD67Enum`, where the suffix is a hash of the choice set.
        #
        # **This pins one name. It does not merge the two.** The client still
        # ships `sexEnum.ts` and `targetProposalRequestSexEnum.ts` with identical
        # members, and an earlier version of this comment claimed otherwise.
        # What the override buys is that neither name is a hash any more, so an
        # unrelated edit to a choice set cannot churn the committed client. That
        # is the same argument the comment above makes for naming enums at all.
        #
        # Merging them would need one serializer field shared by both shapes.
        # Not worth it for two members that have never disagreed.
        "SexEnum": "accounts.models.Sex",
    },
}
