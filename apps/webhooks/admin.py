"""Webhook admin — with reprocessing action."""
from django.contrib import admin, messages

from .models import WebhookEvent
from .processor import process_webhook_event


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "provider_event_id",
        "boleto",
        "authenticity_status",
        "processing_status",
        "attempts",
        "received_at",
    )
    list_filter = ("authenticity_status", "processing_status", "event_type")
    search_fields = (
        "provider_event_id",
        "event_type",
        "boleto__internal_reference",
        "boleto__provider_order_id",
        "boleto__provider_charge_id",
    )
    readonly_fields = (
        "payload",
        "headers_summary",
        "payload_sha256",
        "received_at",
        "processed_at",
    )
    actions = ["reprocess_event"]

    @admin.action(description="Reprocessar evento selecionado")
    def reprocess_event(self, request, queryset):
        count = 0
        for event in queryset:
            if event.processing_status in ("PROCESSED", "IGNORED"):
                # Reset for reprocessing
                event.processing_status = "RECEIVED"
                event.error_code = ""
                event.error_detail = ""
                event.save(update_fields=["processing_status", "error_code", "error_detail"])

            success = process_webhook_event(event)
            if success:
                count += 1
                self.message_user(
                    request,
                    f"Evento {event.event_type} reprocessado com sucesso.",
                    messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    f"Erro ao reprocessar evento {event.event_type}: {event.error_detail}",
                    messages.ERROR,
                )

        self.message_user(request, f"{count} eventos reprocessados.", messages.SUCCESS)
