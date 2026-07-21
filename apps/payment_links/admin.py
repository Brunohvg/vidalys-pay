"""Payment links admin — with attempts inline."""
from django.contrib import admin

from apps.core.admin import TimeStampedModelAdmin

from .models import PaymentAttempt, PaymentLink


class PaymentAttemptInline(admin.TabularInline):
    model = PaymentAttempt
    extra = 0
    readonly_fields = (
        "provider_order_id",
        "provider_charge_id",
        "status",
        "amount_cents",
        "installments",
        "failure_code",
        "failure_message",
        "paid_at",
        "raw_summary",
        "created_at",
    )
    fields = readonly_fields


@admin.register(PaymentLink)
class PaymentLinkAdmin(TimeStampedModelAdmin):
    list_display = (
        "reference",
        "seller",
        "amount_cents",
        "installments",
        "status",
        "provider_link_id",
        "created_at",
    )
    list_filter = ("status", "provider")
    search_fields = ("reference", "seller__name", "provider_link_id")
    readonly_fields = (
        "provider",
        "provider_link_id",
        "payment_url",
        "provider_status",
        "creation_request",
        "creation_response",
        "idempotency_key",
    )
    inlines = [PaymentAttemptInline]


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(TimeStampedModelAdmin):
    list_display = (
        "payment_link",
        "provider_order_id",
        "provider_charge_id",
        "status",
        "amount_cents",
        "paid_at",
    )
    list_filter = ("status",)
    search_fields = ("provider_order_id", "provider_charge_id")
    readonly_fields = (
        "payment_link",
        "provider_order_id",
        "provider_charge_id",
        "raw_summary",
    )
