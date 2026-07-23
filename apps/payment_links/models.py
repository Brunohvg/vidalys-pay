"""Payment link and attempt models."""
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class PaymentLinkStatus(models.TextChoices):
    CREATING = "CREATING", "Criando"
    CREATION_UNKNOWN = "CREATION_UNKNOWN", "Resultado incerto"
    CREATION_ERROR = "CREATION_ERROR", "Erro na criação"
    ACTIVE = "ACTIVE", "Ativo"
    PAID = "PAID", "Pago"
    CANCELED = "CANCELED", "Cancelado"
    EXPIRED = "EXPIRED", "Expirado"
    REFUNDED = "REFUNDED", "Reembolsado"


class PaymentLink(UUIDModel, TimeStampedModel):
    """Link de pagamento criado para um vendedor."""

    seller = models.ForeignKey("sellers.Seller", on_delete=models.PROTECT, related_name="payment_links")
    reference = models.CharField(max_length=80)
    customer_name = models.CharField(max_length=120, blank=True, default="")
    customer_phone = models.CharField(max_length=20, blank=True, default="", help_text="E.164 format")
    description = models.CharField(max_length=255, blank=True, default="")
    amount_cents = models.BigIntegerField()
    installments = models.SmallIntegerField()
    status = models.CharField(
        max_length=20,
        choices=PaymentLinkStatus.choices,
        default=PaymentLinkStatus.CREATING,
        db_index=True,
    )
    provider = models.CharField(max_length=30, default="pagarme")
    provider_link_id = models.CharField(max_length=100, blank=True, default=None, unique=True, null=True)
    payment_url = models.TextField(blank=True, default="")
    provider_status = models.CharField(max_length=80, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    creation_request = models.JSONField(default=dict, blank=True)
    creation_response = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Link de Pagamento"
        verbose_name_plural = "Links de Pagamento"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(installments__gte=1, installments__lte=3), name="installments_range"),
            models.CheckConstraint(condition=models.Q(amount_cents__gt=0), name="amount_positive"),
            models.UniqueConstraint(fields=["seller", "idempotency_key"], name="unique_seller_idempotency"),
        ]

    def __str__(self):
        return f"{self.reference} — {self.get_status_display()}"


class PaymentAttemptStatus(models.TextChoices):
    PENDING = "PENDING", "Aguardando"
    PROCESSING = "PROCESSING", "Processando"
    PAID = "PAID", "Pago"
    FAILED = "FAILED", "Falhou"
    REFUNDED = "REFUNDED", "Reembolsado"
    CHARGEDBACK = "CHARGEDBACK", "Chargeback"


class PaymentAttempt(UUIDModel, TimeStampedModel):
    """Tentativa de pagamento vinculada a um link."""

    payment_link = models.ForeignKey(PaymentLink, on_delete=models.CASCADE, related_name="attempts")
    provider_order_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    provider_charge_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    status = models.CharField(
        max_length=20,
        choices=PaymentAttemptStatus.choices,
        default=PaymentAttemptStatus.PENDING,
    )
    amount_cents = models.BigIntegerField(default=0)
    installments = models.SmallIntegerField(null=True, blank=True)
    failure_code = models.CharField(max_length=100, blank=True, default="")
    failure_message = models.CharField(max_length=255, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)
    raw_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Tentativa de Pagamento"
        verbose_name_plural = "Tentativas de Pagamento"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Tentativa {self.provider_order_id} — {self.get_status_display()}"
