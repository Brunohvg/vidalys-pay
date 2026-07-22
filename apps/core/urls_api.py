"""API v1 URL configuration."""
from django.urls import include, path

app_name = "api_v1"

urlpatterns = [
    path("", include("apps.payment_links.urls_api")),
    path("", include("apps.freight.urls_api")),
    path("webhooks/", include("apps.webhooks.urls")),
]
