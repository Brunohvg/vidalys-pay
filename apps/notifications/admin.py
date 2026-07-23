from django.contrib import admin

from .models import NotificationOutbox, PushSubscription, WhatsAppMessage


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


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("seller", "is_active", "failure_count", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("seller__name", "endpoint")
    readonly_fields = ("created_at", "updated_at", "last_delivery_key")
