from django.apps import AppConfig


class PagarmeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations.pagarme"
    verbose_name = "Integração Pagar.me"
