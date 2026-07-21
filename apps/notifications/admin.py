from django.contrib import admin

from .models import NotificationOutbox, WhatsAppMessage


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ("template_key", "recipient_phone", "status", "attempt_count", "created_at")
    list_filter = ("status",)
    readonly_fields = ("created_at",)


@admin.register(NotificationOutbox)
class NotificationOutboxAdmin(admin.ModelAdmin):
    list_display = ("topic", "aggregate_type", "status", "attempts", "created_at")
    list_filter = ("status", "topic")
    readonly_fields = ("created_at",)
