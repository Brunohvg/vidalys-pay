"""URL configuration for Vidalys Pay."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("painel/", include("apps.admin_panel.urls")),
    path("health/", include("apps.core.urls_health")),
    path("", include("apps.sellers.urls")),
    path("api/v1/", include("apps.core.urls_api")),
]
