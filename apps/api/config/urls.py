"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.views import HealthView, PingView

urlpatterns = [
    path("admin/", admin.site.urls),
    # --- API ---
    path("api/ping/", PingView.as_view(), name="ping"),
    # Probed by Railway's health check (see apps/api/railway.json). Unlike
    # ping, this one queries the database.
    path("api/health/", HealthView.as_view(), name="health"),
    # Sign in with Apple (MAC-27) and the rest of the session lifecycle
    # (MAC-28). `accounts` owns /api/auth/ for session resources and
    # /api/users/ for the user itself -- the URL tree and the app tree are
    # allowed to differ, and forcing them to match is what produced
    # /api/entries/analyze/ in the route audit.
    path("api/auth/", include("accounts.urls")),
    # Same app, second prefix (MAC-28). `accounts` manages both, and that is
    # allowed: the URL tree names resources, the app tree groups code, and they
    # answer different questions.
    path("api/users/", include("accounts.urls_users")),
    # Presigned object-storage URLs (MAC-19). Owns its own routes so the app
    # stays self-contained as more of them appear.
    path("api/targets/", include("targets.urls")),
    path("api/uploads/", include("uploads.urls")),
    # --- OpenAPI schema ---
    # The committed packages/api-client/openapi.json is generated from the same
    # introspection via `manage.py spectacular`; these routes are for humans.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
