"""Boleto administration."""
from django.contrib import admin

from apps.core.admin import TimeStampedModelAdmin

from .models import Boleto, Company


@admin.register(Company)
class CompanyAdmin(TimeStampedModelAdmin):
    list_display = ("legal_name", "cnpj", "trade_name", "city", "state", "updated_at")
    search_fields = ("legal_name", "trade_name", "cnpj")
    list_filter = ("state", "registration_status", "lookup_source")


@admin.register(Boleto)
class BoletoAdmin(TimeStampedModelAdmin):
    list_display = (
        "internal_reference",
        "company",
        "seller",
        "amount_cents",
        "due_date",
        "status",
        "created_at",
    )
    list_filter = ("status", "provider", "due_date")
    search_fields = (
        "internal_reference",
        "company__legal_name",
        "company__cnpj",
        "seller__name",
        "provider_order_id",
        "provider_charge_id",
    )
    readonly_fields = (
        "provider",
        "idempotency_key",
        "provider_order_id",
        "provider_charge_id",
        "provider_transaction_id",
        "provider_status",
        "digitable_line",
        "barcode",
        "pdf_url",
        "company_snapshot",
        "creation_request",
        "creation_response",
        "paid_at",
        "failed_at",
        "expired_at",
        "canceled_at",
    )
