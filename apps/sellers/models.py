"""Seller domain models."""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class Seller(UUIDModel, TimeStampedModel):
    """Vendedor que cria links de pagamento."""

    name = models.CharField(max_length=120)
    whatsapp_phone = models.CharField(max_length=20, help_text="E.164 format")
    is_active = models.BooleanField(default=True)
    max_payment_amount_cents = models.BigIntegerField(help_text="Limite máximo por link em centavos")

    class Meta:
        verbose_name = "Vendedor"
        verbose_name_plural = "Vendedores"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SellerInvitation(UUIDModel, TimeStampedModel):
    """Convite de uso único para acesso do vendedor."""

    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name="invitations")
    token_hash = models.CharField(max_length=64, unique=True, help_text="SHA-256 hash do token")
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invitations",
    )

    class Meta:
        verbose_name = "Convite"
        verbose_name_plural = "Convites"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Convite para {self.seller.name}"


class SellerSession(UUIDModel, TimeStampedModel):
    """Sessão persistente no aparelho do vendedor."""

    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name="sessions")
    django_session_key = models.CharField(max_length=40, unique=True)
    device_label = models.CharField(max_length=120, blank=True, default="")
    user_agent_summary = models.CharField(max_length=255, blank=True, default="")
    ip_first = models.GenericIPAddressField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Sessão do Vendedor"
        verbose_name_plural = "Sessões dos Vendedores"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Sessão de {self.seller.name}"
