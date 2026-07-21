"""Context processors for templates."""
from django.conf import settings


def app_context(request):
    return {
        "app_name": settings.APP_NAME,
        "app_base_url": settings.APP_BASE_URL,
    }
