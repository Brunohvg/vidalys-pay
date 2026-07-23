"""URL configuration for Vidalys Pay."""
from django.contrib import admin
from django.urls import include, path

from apps.core import api_docs

urlpatterns = [
    path("admin/", admin.site.urls),
    path("painel/", include("apps.admin_panel.urls")),
    path("health/", include("apps.core.urls_health")),
    path("api/schema/", api_docs.openapi_schema, name="openapi-schema"),
    path("api/docs/", api_docs.swagger_docs, name="swagger-docs"),
    path("api/redoc/", api_docs.redoc_docs, name="redoc-docs"),
    path("", include("apps.boletos.urls")),
    path("", include("apps.sellers.urls")),
    path("api/v1/", include("apps.payment_links.urls_api")),
    path("api/v1/", include("apps.boletos.urls_api")),
    path("api/v1/", include("apps.freight.urls_api")),
    path("api/v1/webhooks/", include("apps.webhooks.urls")),
]
