"""Company and boleto domain models."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel

cnpj_validator = RegexValidator(
    regex=r"^\d{14}$",
    message="O CNPJ deve conter exatamente 14 dígitos, sem máscara.",
)


class Company(UUIDModel, TimeStampedModel):
    """Pessoa jurídica sacada, identificada globalmente pelo CNPJ normalizado."""

    cnpj = models.CharField(max_length=14, unique=True, validators=[cnpj_validator])
    legal_name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, blank=True, default="")
    registration_status = models.CharField(max_length=40, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    whatsapp_phone = models.CharField(max_length=20, blank=True, default="")
    zip_code = models.CharField(max_length=8)
    street = models.CharField(max_length=200)
    number = models.CharField(max_length=20)
    complement = models.CharField(max_length=100, blank=True, default="")
    district = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    lookup_source = models.CharField(max_length=40, blank=True, default="")
    source_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["legal_name"]

    def __str__(self):
        return f"{self.legal_name} ({self.cnpj})"


class BoletoStatus(models.TextChoices):
    CREATING = "CREATING", "Processando"
    CREATION_UNKNOWN = "CREATION_UNKNOWN", "Confirmação pendente"
    CREATION_ERROR = "CREATION_ERROR", "Erro na emissão"
    PENDING = "PENDING", "Aguardando pagamento"
    PAID = "PAID", "Pago"
    FAILED = "FAILED", "Falhou"
    EXPIRED = "EXPIRED", "Vencido"
    CANCELED = "CANCELED", "Cancelado"
    PARTIALLY_CANCELED = "PARTIALLY_CANCELED", "Parcialmente cancelado"
    REFUNDED = "REFUNDED", "Estornado"


class Boleto(UUIDModel, TimeStampedModel):
    """Cobrança por boleto emitida para uma empresa por um vendedor."""

    seller = models.ForeignKey(
        "sellers.Seller",
        on_delete=models.PROTECT,
        related_name="boletos",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="boletos",
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="boletos_created",
    )
    created_by_seller = models.ForeignKey(
        "sellers.Seller",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="self_created_boletos",
    )
    amount_cents = models.BigIntegerField()
    due_date = models.DateField()
    description = models.CharField(max_length=255)
    internal_reference = models.CharField(max_length=80, blank=True, default="")
    internal_notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=24,
        choices=BoletoStatus.choices,
        default=BoletoStatus.CREATING,
        db_index=True,
    )
    provider = models.CharField(max_length=30, default="pagarme")
    idempotency_key = models.CharField(max_length=100)
    provider_order_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    provider_charge_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    provider_transaction_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    provider_status = models.CharField(max_length=80, blank=True, default="")
    digitable_line = models.CharField(max_length=120, blank=True, default="")
    barcode = models.CharField(max_length=120, blank=True, default="")
    pdf_url = models.URLField(max_length=500, blank=True, default="")
    company_snapshot = models.JSONField(default=dict)
    creation_request = models.JSONField(default=dict, blank=True)
    creation_response = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Boleto"
        verbose_name_plural = "Boletos"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_cents__gt=0),
                name="boleto_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(created_by_user__isnull=False, created_by_seller__isnull=True)
                    | models.Q(created_by_user__isnull=True, created_by_seller__isnull=False)
                ),
                name="boleto_exactly_one_creator",
            ),
            models.UniqueConstraint(
                fields=["seller", "idempotency_key"],
                name="unique_boleto_seller_idempotency",
            ),
        ]
        indexes = [
            models.Index(fields=["seller", "status"], name="boleto_seller_status_idx"),
            models.Index(fields=["due_date"], name="boleto_due_date_idx"),
            models.Index(fields=["company", "created_at"], name="boleto_company_created_idx"),
        ]

    def clean(self):
        super().clean()
        if bool(self.created_by_user_id) == bool(self.created_by_seller_id):
            raise ValidationError("O boleto deve possuir exatamente um ator criador.")
        if self.created_by_seller_id and self.created_by_seller_id != self.seller_id:
            raise ValidationError(
                {"created_by_seller": "O vendedor só pode criar boletos para si próprio."}
            )

    def __str__(self):
        return f"{self.internal_reference or self.id} — {self.get_status_display()}"
