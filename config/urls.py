"""URL configuration for Vidalys Pay."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("painel/", include("apps.admin_panel.urls")),
    path("health/", include("apps.core.urls_health")),
    path("", include("apps.sellers.urls")),
    path("api/v1/", include("apps.payment_links.urls_api")),
    path("api/v1/", include("apps.freight.urls_api")),
    path("api/v1/webhooks/", include("apps.webhooks.urls")),
]
