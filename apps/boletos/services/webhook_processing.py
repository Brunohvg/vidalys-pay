"""Reconcile boleto state from the existing Pagar.me webhook stream."""

import logging

from django.db import transaction
from django.utils import timezone

from apps.boletos.models import Boleto, BoletoStatus
from apps.webhooks.models import ProcessingStatus, WebhookEvent

logger = logging.getLogger("apps.webhooks")


EVENT_STATUS = {
    "order.created": BoletoStatus.PENDING,
    "order.paid": BoletoStatus.PAID,
    "order.payment_failed": BoletoStatus.FAILED,
    "order.canceled": BoletoStatus.CANCELED,
    "charge.created": BoletoStatus.PENDING,
    "charge.pending": BoletoStatus.PENDING,
    "charge.paid": BoletoStatus.PAID,
    "charge.payment_failed": BoletoStatus.FAILED,
    "charge.failed": BoletoStatus.FAILED,
    "charge.canceled": BoletoStatus.CANCELED,
    "charge.partial_canceled": BoletoStatus.PARTIALLY_CANCELED,
    "charge.refunded": BoletoStatus.REFUNDED,
}

NOTIFICATION_EVENTS = {
    BoletoStatus.PAID: "boleto_paid",
    BoletoStatus.FAILED: "boleto_failed",
    BoletoStatus.EXPIRED: "boleto_expired",
    BoletoStatus.CANCELED: "boleto_canceled",
    BoletoStatus.PARTIALLY_CANCELED: "boleto_partially_canceled",
    BoletoStatus.REFUNDED: "boleto_refunded",
}

ALLOWED_TRANSITIONS = {
    BoletoStatus.CREATING: {
        BoletoStatus.PENDING,
        BoletoStatus.PAID,
        BoletoStatus.FAILED,
        BoletoStatus.CANCELED,
        BoletoStatus.EXPIRED,
        BoletoStatus.CREATION_ERROR,
        BoletoStatus.CREATION_UNKNOWN,
    },
    BoletoStatus.CREATION_UNKNOWN: {
        BoletoStatus.PENDING,
        BoletoStatus.PAID,
        BoletoStatus.FAILED,
        BoletoStatus.CANCELED,
        BoletoStatus.EXPIRED,
    },
    BoletoStatus.CREATION_ERROR: {
        BoletoStatus.PENDING,
        BoletoStatus.PAID,
        BoletoStatus.FAILED,
        BoletoStatus.CANCELED,
        BoletoStatus.EXPIRED,
    },
    BoletoStatus.PENDING: {
        BoletoStatus.PAID,
        BoletoStatus.FAILED,
        BoletoStatus.EXPIRED,
        BoletoStatus.CANCELED,
        BoletoStatus.PARTIALLY_CANCELED,
    },
    BoletoStatus.FAILED: {BoletoStatus.PENDING, BoletoStatus.PAID},
    BoletoStatus.EXPIRED: {BoletoStatus.PAID},
    BoletoStatus.PAID: {BoletoStatus.PARTIALLY_CANCELED, BoletoStatus.REFUNDED},
    BoletoStatus.PARTIALLY_CANCELED: {BoletoStatus.CANCELED, BoletoStatus.REFUNDED},
    BoletoStatus.CANCELED: set(),
    BoletoStatus.REFUNDED: set(),
}


def find_boleto(normalized) -> Boleto | None:
    """Find the aggregate by trusted internal metadata, then provider IDs."""
    if normalized.internal_boleto_id:
        try:
            return Boleto.objects.filter(pk=normalized.internal_boleto_id).first()
        except (TypeError, ValueError):
            return None

    if normalized.charge_id:
        boleto = Boleto.objects.filter(provider_charge_id=normalized.charge_id).first()
        if boleto:
            return boleto

    if normalized.order_id:
        return Boleto.objects.filter(provider_order_id=normalized.order_id).first()

    return None


def is_boleto_event(normalized, boleto: Boleto | None) -> bool:
    """Only claim events explicitly correlated with the boleto aggregate."""
    return bool(normalized.internal_boleto_id or boleto)


def process_boleto_event(event: WebhookEvent, normalized, boleto: Boleto | None) -> bool:
    """Process one event atomically and leave an auditable event-to-boleto link."""
    if boleto is None:
        _finish_event(
            event,
            ProcessingStatus.FAILED,
            error_code="BOLETO_NOT_FOUND",
        )
        return False

    with transaction.atomic():
        boleto = Boleto.objects.select_for_update().get(pk=boleto.pk)
        if _has_provider_id_mismatch(boleto, normalized):
            _finish_event(
                event,
                ProcessingStatus.FAILED,
                boleto=boleto,
                error_code="BOLETO_PROVIDER_ID_MISMATCH",
            )
            return False

        target_status = resolve_target_status(event.event_type, normalized)
        changed_fields = _reconcile_provider_ids(boleto, normalized)
        status_changed = target_status is not None and target_status != boleto.status

        event.boleto = boleto
        if target_status is None:
            if changed_fields:
                boleto.save(update_fields=[*changed_fields, "updated_at"])
            _finish_event(event, ProcessingStatus.IGNORED, boleto=boleto)
            return True

        if target_status != boleto.status:
            allowed = ALLOWED_TRANSITIONS.get(boleto.status, set())
            if target_status not in allowed:
                logger.info(
                    "Transição de boleto ignorada: boleto=%s %s -> %s evento=%s",
                    boleto.id,
                    boleto.status,
                    target_status,
                    event.event_type,
                )
                if changed_fields:
                    boleto.save(update_fields=[*changed_fields, "updated_at"])
                _finish_event(event, ProcessingStatus.IGNORED, boleto=boleto)
                return True

            boleto.status = target_status
            changed_fields.append("status")
        timestamp_field = {
            BoletoStatus.PAID: "paid_at",
            BoletoStatus.FAILED: "failed_at",
            BoletoStatus.EXPIRED: "expired_at",
            BoletoStatus.CANCELED: "canceled_at",
            BoletoStatus.REFUNDED: "refunded_at",
        }.get(target_status)
        if timestamp_field and getattr(boleto, timestamp_field) is None:
            setattr(boleto, timestamp_field, timezone.now())
            changed_fields.append(timestamp_field)

        provider_status = normalized.status or target_status.lower()
        if boleto.provider_status != provider_status:
            boleto.provider_status = provider_status
            changed_fields.append("provider_status")

        if changed_fields:
            boleto.save(update_fields=[*dict.fromkeys(changed_fields), "updated_at"])

        _finish_event(event, ProcessingStatus.PROCESSED, boleto=boleto)
        logger.info(
            "boleto_webhook_processed=true boleto=%s event=%s provider_event=%s status=%s",
            boleto.id,
            event.event_type,
            event.provider_event_id,
            boleto.status,
        )
        if status_changed and target_status in NOTIFICATION_EVENTS:
            transaction.on_commit(
                lambda boleto_id=boleto.id, notification_event=NOTIFICATION_EVENTS[
                    target_status
                ]: _queue_status_notification(boleto_id, notification_event),
                robust=True,
            )
        return True


def resolve_target_status(event_type: str, normalized) -> str | None:
    """Resolve state without inferring expiry from an order closure alone."""
    if event_type != "order.closed":
        return EVENT_STATUS.get(event_type)

    statuses = {
        str(status).strip().lower()
        for status in (
            normalized.charge_status,
            normalized.transaction_status,
            normalized.status,
        )
        if status
    }
    for provider_statuses, boleto_status in (
        ({"paid", "captured"}, BoletoStatus.PAID),
        ({"canceled", "cancelled", "voided"}, BoletoStatus.CANCELED),
        ({"expired", "overdue"}, BoletoStatus.EXPIRED),
        ({"failed", "payment_failed", "not_authorized"}, BoletoStatus.FAILED),
    ):
        if statuses & provider_statuses:
            return boleto_status
    return None


def _has_provider_id_mismatch(boleto: Boleto, normalized) -> bool:
    """Reject conflicting IDs before changing the aggregate."""
    for field, incoming in (
        ("provider_order_id", normalized.order_id),
        ("provider_charge_id", normalized.charge_id),
        ("provider_transaction_id", normalized.transaction_id),
    ):
        current = getattr(boleto, field)
        if current and incoming and current != incoming:
            return True
        if incoming and Boleto.objects.exclude(pk=boleto.pk).filter(**{field: incoming}).exists():
            return True
    return False


def _reconcile_provider_ids(boleto: Boleto, normalized) -> list[str]:
    changed_fields = []
    for field, value in (
        ("provider_order_id", normalized.order_id),
        ("provider_charge_id", normalized.charge_id),
        ("provider_transaction_id", normalized.transaction_id),
    ):
        if value and not getattr(boleto, field):
            setattr(boleto, field, value)
            changed_fields.append(field)
    return changed_fields


def _finish_event(
    event: WebhookEvent,
    status: str,
    *,
    boleto: Boleto | None = None,
    error_code: str = "",
) -> None:
    event.boleto = boleto
    event.processing_status = status
    event.error_code = error_code
    event.error_detail = ""
    event.processed_at = timezone.now()
    event.save(
        update_fields=[
            "boleto",
            "processing_status",
            "error_code",
            "error_detail",
            "processed_at",
        ]
    )


def _queue_status_notification(boleto_id, event_type: str) -> None:
    from apps.notifications.whatsapp_service import queue_boleto_status

    boleto = Boleto.objects.select_related("seller").get(pk=boleto_id)
    queue_boleto_status(boleto=boleto, event_type=event_type)
