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
    "order.closed": BoletoStatus.EXPIRED,
    "charge.created": BoletoStatus.PENDING,
    "charge.pending": BoletoStatus.PENDING,
    "charge.paid": BoletoStatus.PAID,
    "charge.payment_failed": BoletoStatus.FAILED,
    "charge.failed": BoletoStatus.FAILED,
    "charge.canceled": BoletoStatus.CANCELED,
    "charge.partial_canceled": BoletoStatus.PARTIALLY_CANCELED,
    "charge.refunded": BoletoStatus.REFUNDED,
}

ALLOWED_TRANSITIONS = {
    BoletoStatus.CREATING: set(BoletoStatus.values),
    BoletoStatus.CREATION_UNKNOWN: set(BoletoStatus.values),
    BoletoStatus.CREATION_ERROR: {BoletoStatus.PENDING, BoletoStatus.PAID},
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
        target_status = EVENT_STATUS.get(event.event_type)
        changed_fields = _reconcile_provider_ids(boleto, normalized)

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
        return True


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
