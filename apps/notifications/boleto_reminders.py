"""Periodic, idempotent boleto due-date reminders."""

import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.boletos.models import Boleto, BoletoStatus

from .push_service import queue_boleto_reminder_push
from .whatsapp_service import queue_boleto_reminder

logger = logging.getLogger("apps.notifications.reminders")


def scan_boleto_reminders(*, today: date | None = None) -> int:
    """Queue configured reminders for pending boletos and return matches scanned."""
    if not settings.BOLETO_REMINDERS_ENABLED:
        return 0

    today = today or timezone.localdate(
        timezone=ZoneInfo(settings.BOLETO_REMINDER_TIME_ZONE)
    )
    matched = 0
    for days_until_due in settings.BOLETO_REMINDER_DAYS:
        due_date = today + timedelta(days=days_until_due)
        boletos = (
            Boleto.objects.filter(status=BoletoStatus.PENDING, due_date=due_date)
            .select_related("seller", "company")
            .iterator(chunk_size=200)
        )
        for boleto in boletos:
            matched += 1
            push_created = queue_boleto_reminder_push(
                boleto=boleto,
                days_until_due=days_until_due,
            )
            whatsapp_results = []
            if settings.BOLETO_REMINDER_WHATSAPP_ENABLED:
                whatsapp_results = queue_boleto_reminder(
                    boleto=boleto,
                    days_until_due=days_until_due,
                )
            logger.info(
                "boleto_reminder_scanned=true boleto=%s days_until_due=%s push_created=%s whatsapp=%s",
                boleto.id,
                days_until_due,
                push_created,
                ",".join(result.status for result in whatsapp_results) or "disabled",
            )
    return matched
