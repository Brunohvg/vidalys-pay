"""Webhook event models."""
from django.db import models

from apps.core.models import UUIDModel


class AuthenticityStatus(models.TextChoices):
    VERIFIED = "VERIFIED", "Verificado"
    UNVERIFIED = "UNVERIFIED", "Não verificado"
    INVALID = "INVALID", "Inválido"


class ProcessingStatus(models.TextChoices):
    RECEIVED = "RECEIVED", "Recebido"
    PROCESSED = "PROCESSED", "Processado"
    IGNORED = "IGNORED", "Ignorado"
    FAILED = "FAILED", "Falhou"


class WebhookEvent(UUIDModel):
    """Evento bruto recebido de webhook externo."""

    provider = models.CharField(max_length=30, default="pagarme")
    boleto = models.ForeignKey(
        "boletos.Boleto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_events",
    )
    provider_event_id = models.CharField(max_length=120, blank=True, default="", unique=True, null=True)
    event_type = models.CharField(max_length=120)
    payload = models.JSONField()
    payload_sha256 = models.CharField(max_length=64)
    headers_summary = models.JSONField(default=dict, blank=True)
    authenticity_status = models.CharField(
        max_length=20,
        choices=AuthenticityStatus.choices,
        default=AuthenticityStatus.UNVERIFIED,
    )
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.RECEIVED,
    )
    attempts = models.IntegerField(default=0)
    error_code = models.CharField(max_length=100, blank=True, default="")
    error_detail = models.TextField(blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Evento de Webhook"
        verbose_name_plural = "Eventos de Webhook"
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.event_type} — {self.get_processing_status_display()}"
