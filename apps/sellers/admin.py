"""Seller admin with actions."""
from django.contrib import admin, messages
from django.utils import timezone

from apps.core.admin import TimeStampedModelAdmin
from apps.notifications.whatsapp_service import queue_invitation

from .models import Seller, SellerInvitation, SellerSession
from .services import generate_invitation, revoke_all_sessions


@admin.register(Seller)
class SellerAdmin(TimeStampedModelAdmin):
    list_display = ("name", "whatsapp_phone", "is_active", "max_payment_amount_cents")
    list_filter = ("is_active",)
    search_fields = ("name", "whatsapp_phone")
    actions = ["send_invitation", "revoke_access_and_send_invitation"]

    @admin.action(description="Enviar convite de acesso")
    def send_invitation(self, request, queryset):
        for seller in queryset:
            if not seller.is_active:
                self.message_user(request, f"{seller.name} está inativo. Convite não enviado.", messages.WARNING)
                continue

            invitation, raw_token = generate_invitation(seller=seller, created_by=request.user)

            activation_url = f"{request.build_absolute_uri('/acesso/')}{raw_token}"
            queue_invitation(seller=seller, activation_url=activation_url)

            self.message_user(
                request,
                f"Convite gerado para {seller.name}. URL: {activation_url}",
                messages.SUCCESS,
            )

    @admin.action(description="Revogar acessos e enviar novo convite")
    def revoke_access_and_send_invitation(self, request, queryset):
        for seller in queryset:
            count = revoke_all_sessions(seller=seller)
            invitation, raw_token = generate_invitation(seller=seller, created_by=request.user)

            activation_url = f"{request.build_absolute_uri('/acesso/')}{raw_token}"
            queue_invitation(seller=seller, activation_url=activation_url)

            self.message_user(
                request,
                f"{count} sessões revogadas para {seller.name}. Novo convite: {activation_url}",
                messages.SUCCESS,
            )


@admin.register(SellerInvitation)
class SellerInvitationAdmin(TimeStampedModelAdmin):
    list_display = ("seller", "expires_at", "used_at", "revoked_at")
    list_filter = ("used_at", "revoked_at")
    readonly_fields = ("token_hash", "created_by")


@admin.register(SellerSession)
class SellerSessionAdmin(TimeStampedModelAdmin):
    list_display = ("seller", "device_label", "expires_at", "revoked_at")
    list_filter = ("revoked_at",)
    actions = ["revoke_sessions"]

    @admin.action(description="Revogar sessões selecionadas")
    def revoke_sessions(self, request, queryset):
        now = timezone.now()
        count = 0
        for session in queryset.filter(revoked_at__isnull=True):
            # Delete Django session
            from django.contrib.sessions.backends.db import SessionStore

            try:
                store = SessionStore(session_key=session.django_session_key)
                store.delete()
            except Exception:
                pass

            session.revoked_at = now
            session.save(update_fields=["revoked_at"])
            count += 1

        self.message_user(request, f"{count} sessões revogadas.", messages.SUCCESS)
