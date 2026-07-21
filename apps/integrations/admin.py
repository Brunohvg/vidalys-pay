"""Integrations admin — ApiClient moved to n8n app."""
from django.contrib import admin

from apps.integrations.n8n.models import ApiClient


@admin.register(ApiClient)
class ApiClientAdmin(admin.ModelAdmin):
    list_display = ("name", "key_prefix", "is_active", "last_used_at")
    list_filter = ("is_active",)
    readonly_fields = ("key_hash", "last_used_at", "created_at")
