"""Outbox worker â€” processes pending notifications.

Uses SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent processing.
"""
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("apps.notifications.worker")

BACKOFF_SECONDS = [0, 60, 300, 900, 3600]


class Command(BaseCommand):
    help = "Processa itens pendentes do outbox de notificaÃ§Ãµes"

    def handle(self, *args, **options):
        logger.info("Outbox worker iniciado")
        self._recover_stale_items()
        next_reminder_scan = None
        while True:
            now = timezone.now()
            if next_reminder_scan is None or now >= next_reminder_scan:
                self._scan_boleto_reminders()
                next_reminder_scan = now + timedelta(
                    seconds=max(settings.BOLETO_REMINDER_SCAN_SECONDS, 60)
                )
            processed = self._process_batch()
            if not processed:
                time.sleep(settings.WORKER_POLL_SECONDS)

    def _scan_boleto_reminders(self):
        from apps.notifications.boleto_reminders import scan_boleto_reminders

        try:
            matched = scan_boleto_reminders()
            if matched:
                logger.info("Lembretes de boleto avaliados: %d", matched)
        except Exception:
            logger.exception("Falha ao avaliar lembretes de boleto")

    def _recover_stale_items(self):
        from apps.notifications.models import NotificationOutbox

        cutoff = timezone.now() - timedelta(seconds=settings.OUTBOX_STALE_LOCK_SECONDS)
        recovered = NotificationOutbox.objects.filter(
            status="PROCESSING",
            locked_at__lt=cutoff,
        ).update(status="PENDING", locked_at=None, locked_by="", available_at=timezone.now())
        if recovered:
            logger.warning("Outbox: %d itens PROCESSING obsoletos recuperados", recovered)

    def _process_batch(self):
        from apps.notifications.models import NotificationOutbox

        now = timezone.now()
        with transaction.atomic():
            items = list(
                NotificationOutbox.objects.select_for_update(skip_locked=True)
                .filter(status="PENDING", available_at__lte=now)
                .order_by("available_at")[:10]
            )
            for item in items:
                item.status = "PROCESSING"
                item.locked_by = "worker"
                item.locked_at = now
                item.save(update_fields=["status", "locked_by", "locked_at"])

        # Network I/O must happen after releasing the database row locks.
        for item in items:
            self._process_item(item)

        return bool(items)

    def _process_item(self, item):
        try:
            success = self._dispatch(item)
            if success:
                item.status = "DONE"
                item.processed_at = timezone.now()
                item.save(update_fields=["status", "processed_at"])
            else:
                self._handle_failure(item)
        except Exception as e:
            logger.exception("Erro ao processar outbox %s", item.id)
            item.last_error = str(e)[:255]
            self._handle_failure(item)

    def _dispatch(self, item):
        """Dispatch based on topic."""
        if item.topic == "whatsapp.send":
            return self._send_whatsapp(item)
        if item.topic == "webpush.send":
            from apps.notifications.push_service import send_push_outbox_item

            return send_push_outbox_item(item)
        item.last_error = f"Tópico desconhecido: {item.topic}"[:255]
        logger.error("Tópico desconhecido: %s", item.topic)
        return False

    def _send_whatsapp(self, item):
        """Send WhatsApp message via Evolution API."""
        from apps.integrations.evolution.client import EvolutionClient, EvolutionError
        from apps.notifications.models import WhatsAppMessage, WhatsAppMessageStatus

        payload = item.payload
        message_id = payload.get("message_id")
        phone = payload.get("phone")
        text = payload.get("text")

        if not all([message_id, phone, text]):
            logger.error("Payload incompleto para outbox %s", item.id)
            return False

        # Update message status to SENDING
        try:
            message = WhatsAppMessage.objects.get(id=message_id)
            message.status = WhatsAppMessageStatus.SENDING
            message.save(update_fields=["status"])
        except WhatsAppMessage.DoesNotExist:
            logger.error("Mensagem %s nÃ£o encontrada", message_id)
            return False

        # Send via Evolution
        try:
            client = EvolutionClient()
            response = client.send_text(phone=phone, text=text)

            # Update message with response
            provider_message_id = response.get("key", {}).get("id", "")
            message.status = WhatsAppMessageStatus.SENT
            message.provider_message_id = provider_message_id
            message.provider_status = response.get("status", "")
            message.sent_at = timezone.now()
            message.attempt_count += 1
            message.save()

            logger.info("WhatsApp enviado: %s â†’ %s", message_id, provider_message_id)
            return True

        except EvolutionError as e:
            logger.error("Evolution erro para %s: %s", message_id, e)
            message.status = WhatsAppMessageStatus.FAILED
            message.last_error = str(e)[:255]
            message.attempt_count += 1
            message.save(update_fields=["status", "last_error", "attempt_count"])
            return False

        except Exception as e:
            logger.exception("Erro inesperado ao enviar WhatsApp %s", message_id)
            message.status = WhatsAppMessageStatus.FAILED
            message.last_error = str(e)[:255]
            message.attempt_count += 1
            message.save(update_fields=["status", "last_error", "attempt_count"])
            return False

    def _handle_failure(self, item):
        item.attempts += 1
        if item.attempts >= settings.MAX_NOTIFICATION_ATTEMPTS:
            item.status = "DEAD"
            # Mark final message status
            self._mark_message_dead(item)
        else:
            item.status = "PENDING"
            backoff_index = min(item.attempts, len(BACKOFF_SECONDS) - 1)
            item.available_at = timezone.now() + timezone.timedelta(seconds=BACKOFF_SECONDS[backoff_index])
        item.locked_at = None
        item.locked_by = ""
        item.save(update_fields=["status", "attempts", "last_error", "available_at", "locked_at", "locked_by"])

    def _mark_message_dead(self, item):
        """Mark WhatsApp message as DEAD when outbox is exhausted."""
        from apps.notifications.models import WhatsAppMessage, WhatsAppMessageStatus

        message_id = item.payload.get("message_id")
        if message_id:
            try:
                message = WhatsAppMessage.objects.get(id=message_id)
                message.status = WhatsAppMessageStatus.DEAD
                message.save(update_fields=["status"])
            except WhatsAppMessage.DoesNotExist:
                pass
