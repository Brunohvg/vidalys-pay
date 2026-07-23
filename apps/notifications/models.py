"""Notification and outbox models."""
from django.db import models

from apps.core.models import UUIDModel


class WhatsAppMessageStatus(models.TextChoices):
    QUEUED = "QUEUED", "Na fila"
    SENDING = "SENDING", "Enviando"
    SENT = "SENT", "Enviado"
    FAILED = "FAILED", "Falhou"
    DEAD = "DEAD", "Permanente"


class RecipientType(models.TextChoices):
    SELLER = "seller", "Vendedor"
    CUSTOMER = "customer", "Cliente"


class WhatsAppMessage(UUIDModel):
    """Mensagem enviada ou enfileirada para WhatsApp."""

    seller = models.ForeignKey("sellers.Seller", on_delete=models.CASCADE, related_name="whatsapp_messages")
    payment_link = models.ForeignKey(
        "payment_links.PaymentLink",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_messages",
    )
    template_key = models.CharField(max_length=80)
    event_type = models.CharField(max_length=80, blank=True, default="")
    recipient_type = models.CharField(
        max_length=20,
        choices=RecipientType.choices,
        default=RecipientType.SELLER,
    )
    recipient_phone = models.CharField(max_length=20)
    rendered_text = models.TextField()
    provider_message_id = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=WhatsAppMessageStatus.choices,
        default=WhatsAppMessageStatus.QUEUED,
    )
    provider_status = models.CharField(max_length=80, blank=True, default="")
    attempt_count = models.IntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mensagem WhatsApp"
        verbose_name_plural = "Mensagens WhatsApp"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.template_key} â†’ {self.recipient_type}:{self.recipient_phone}"


class OutboxStatus(models.TextChoices):
    PENDING = "PENDING", "Pendente"
    PROCESSING = "PROCESSING", "Processando"
    DONE = "DONE", "ConcluÃ­do"
    DEAD = "DEAD", "Permanente"


class NotificationOutbox(UUIDModel):
    """Outbox para envio confiÃ¡vel de mensagens."""

    topic = models.CharField(max_length=80)
    aggregate_type = models.CharField(max_length=80)
    aggregate_id = models.UUIDField(db_index=True)
    deduplication_key = models.CharField(max_length=200, unique=True)
    payload = models.JSONField()
    status = models.CharField(
        max_length=20,
        choices=OutboxStatus.choices,
        default=OutboxStatus.PENDING,
        db_index=True,
    )
    available_at = models.DateTimeField(auto_now_add=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=100, blank=True, default="")
    attempts = models.IntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Outbox de NotificaÃ§Ã£o"
        verbose_name_plural = "Outbox de NotificaÃ§Ãµes"
        ordering = ["available_at"]

    def __str__(self):
        return f"{self.topic} â€” {self.get_status_display()}"
class PushSubscription(UUIDModel):
    """Web Push subscription for one seller device/browser profile."""

    seller = models.ForeignKey(
        "sellers.Seller",
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    user_agent = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    failure_count = models.PositiveSmallIntegerField(default=0)
    last_delivery_key = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Assinatura Push"
        verbose_name_plural = "Assinaturas Push"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Push de {self.seller.name}"
