"""n8n integration models — API client keys for external integrations."""
from django.db import models

from apps.core.models import UUIDModel


class ApiClient(UUIDModel):
    """Chave de API para integrações externas (ex: n8n)."""

    name = models.CharField(max_length=120)
    key_prefix = models.CharField(max_length=12, help_text="Prefixo visual para identificação")
    key_hash = models.CharField(max_length=64, help_text="SHA-256 hash da chave")
    scopes = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cliente API"
        verbose_name_plural = "Clientes API"

    def __str__(self):
        return self.name
