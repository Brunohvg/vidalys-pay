"""Freight app configuration."""
from django.apps import AppConfig


class FreightConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.freight"
    verbose_name = "Frete"

    def ready(self):
        from . import checks  # noqa: F401
