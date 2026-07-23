"""Webhook event processor â€” maps events to state transitions."""
import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.boletos.services.webhook_processing import (
    find_boleto,
    is_boleto_event,
    process_boleto_event,
)
from apps.notifications.push_service import queue_payment_status_push
from apps.notifications.whatsapp_service import (
    queue_payment_approved,
    queue_payment_canceled,
    queue_payment_chargedback,
    queue_payment_expired,
    queue_payment_failed,
    queue_payment_refunded,
)
from apps.payment_links.models import PaymentAttempt, PaymentLink, PaymentLinkStatus

from .event_mapping import FINAL_STATES, NO_REGRESS_STATES, get_event_config
from .models import ProcessingStatus, WebhookEvent
from .pagarme_payload import normalize_event

logger = logging.getLogger("apps.webhooks")


def process_webhook_event(event: WebhookEvent) -> bool:
    """Process a webhook event.

    Called via transaction.on_commit â€” the event is already persisted.
    """
    WebhookEvent.objects.filter(pk=event.pk).update(attempts=F("attempts") + 1)
    normalized = normalize_event(event.payload)
    boleto = find_boleto(normalized)

    if is_boleto_event(normalized, boleto):
        try:
            return process_boleto_event(event, normalized, boleto)
        except Exception:
            logger.exception(
                "Erro ao processar evento %s para boleto=%s",
                event.event_type,
                boleto.id if boleto else None,
            )
            event.processing_status = ProcessingStatus.FAILED
            event.error_code = "PROCESSING_ERROR"
            event.error_detail = ""
            event.save(update_fields=["processing_status", "error_code", "error_detail"])
            return False

    payment_link = _find_payment_link(event, normalized)
    has_internal_link_reference = bool(normalized.internal_payment_link_id)
    config = get_event_config(event.event_type)

    if config is None:
        return _ignore_or_discard(
            event,
            correlated=payment_link is not None or has_internal_link_reference,
            reason="unknown_event_type",
        )

    action = config.get("action", "ignore")

    if action == "ignore":
        return _ignore_or_discard(
            event,
            correlated=payment_link is not None or has_internal_link_reference,
            reason="configured_ignore",
        )

    if payment_link is None:
        return _ignore_or_discard(
            event,
            correlated=has_internal_link_reference,
            reason="payment_link_not_found",
        )

    # Guard: never regress final states
    current_status = payment_link.status
    target_status = config.get("link_status", "")
    if target_status and current_status in NO_REGRESS_STATES:
        logger.info(
            "TransiÃ§Ã£o bloqueada (estado final): link=%s %s -> %s evento=%s",
            payment_link.id, current_status, target_status, event.event_type,
        )
        event.processing_status = ProcessingStatus.IGNORED
        event.processed_at = timezone.now()
        event.save(update_fields=["processing_status", "processed_at"])
        return True

    try:
        with transaction.atomic():
            handler = ACTION_HANDLERS.get(action)
            if handler is None:
                logger.warning("AÃ§Ã£o desconhecida: %s", action)
                event.processing_status = ProcessingStatus.IGNORED
                event.processed_at = timezone.now()
                event.save(update_fields=["processing_status", "processed_at"])
                return True

            handler(event, payment_link, config, normalized)

            event.processing_status = ProcessingStatus.PROCESSED
            event.processed_at = timezone.now()
            event.save(update_fields=["processing_status", "processed_at"])

            return True

    except Exception:
        logger.exception("Erro ao processar evento %s link=%s", event.event_type, payment_link.id)
        event.processing_status = ProcessingStatus.FAILED
        event.error_code = "PROCESSING_ERROR"
        event.error_detail = ""
        event.save(update_fields=["processing_status", "error_code", "error_detail"])
        return False


def _ignore_or_discard(
    event: WebhookEvent,
    *,
    correlated: bool,
    reason: str,
) -> bool:
    """Retain owned ignored events and discard events unrelated to Vidalys Pay."""
    if correlated:
        logger.info(
            "Webhook correlacionado ignorado: id=%s type=%s reason=%s",
            event.provider_event_id,
            event.event_type,
            reason,
        )
        event.processing_status = ProcessingStatus.IGNORED
        event.processed_at = timezone.now()
        event.save(update_fields=["processing_status", "processed_at"])
        return True

    provider_event_id = event.provider_event_id
    event_type = event.event_type
    event.delete()
    logger.info(
        "Webhook externo descartado: id=%s type=%s reason=%s",
        provider_event_id,
        event_type,
        reason,
    )
    return True


def _handle_mark_paid(event, payment_link, config, normalized):
    payment_link.status = PaymentLinkStatus.PAID
    payment_link.paid_at = timezone.now()
    payment_link.provider_status = normalized.status or "paid"
    payment_link.save(update_fields=["status", "paid_at", "provider_status", "updated_at"])

    attempt = _create_or_update_attempt(event, payment_link, config, normalized)

    from django.db import transaction as txn
    txn.on_commit(lambda: queue_payment_approved(
        seller=payment_link.seller, payment_link=payment_link,
    ))
    txn.on_commit(lambda: queue_payment_status_push(
        payment_link=payment_link, event_type="payment_paid",
    ))

    logger.info("Link %s marcado como PAID, attempt=%s", payment_link.id, attempt.id)


def _handle_create_attempt(event, payment_link, config, normalized):
    attempt = _create_or_update_attempt(event, payment_link, config, normalized)

    if config.get("attempt_status") == "FAILED":
        from django.db import transaction as txn
        reason = normalized.failure.public_message if normalized.failure else ""
        charge_id = normalized.charge_id or ""
        txn.on_commit(lambda: queue_payment_failed(
            seller=payment_link.seller, payment_link=payment_link,
            failure_reason=reason, dedup_suffix=charge_id,
        ))
        txn.on_commit(lambda: queue_payment_status_push(
            payment_link=payment_link, event_type="payment_failed", dedup_suffix=charge_id,
        ))

    if config.get("attempt_status") == "PAID":
        payment_link.status = PaymentLinkStatus.PAID
        payment_link.paid_at = timezone.now()
        payment_link.provider_status = normalized.status or "paid"
        payment_link.save(update_fields=["status", "paid_at", "provider_status", "updated_at"])

        from django.db import transaction as txn
        txn.on_commit(lambda: queue_payment_approved(
            seller=payment_link.seller, payment_link=payment_link,
        ))
        txn.on_commit(lambda: queue_payment_status_push(
            payment_link=payment_link, event_type="payment_paid",
        ))

    if config.get("attempt_status") == "CHARGEDBACK":
        from django.db import transaction as txn
        charge_id = normalized.charge_id or ""
        txn.on_commit(lambda: queue_payment_chargedback(
            seller=payment_link.seller, payment_link=payment_link,
            dedup_suffix=charge_id,
        ))
        txn.on_commit(lambda: queue_payment_status_push(
            payment_link=payment_link, event_type="payment_chargedback", dedup_suffix=charge_id,
        ))

    logger.info("Attempt %s criado/atualizado para link %s", attempt.id, payment_link.id)


def _handle_mark_canceled(event, payment_link, config, normalized):
    payment_link.status = PaymentLinkStatus.CANCELED
    payment_link.canceled_at = timezone.now()
    payment_link.provider_status = normalized.status or "canceled"
    payment_link.save(update_fields=["status", "canceled_at", "provider_status", "updated_at"])

    from django.db import transaction as txn
    txn.on_commit(lambda: queue_payment_canceled(
        seller=payment_link.seller, payment_link=payment_link,
    ))
    txn.on_commit(lambda: queue_payment_status_push(
        payment_link=payment_link, event_type="payment_canceled",
    ))

    logger.info("Link %s marcado como CANCELADO", payment_link.id)


def _handle_mark_refunded(event, payment_link, config, normalized):
    payment_link.status = PaymentLinkStatus.REFUNDED
    payment_link.refunded_at = timezone.now()
    payment_link.save(update_fields=["status", "refunded_at", "updated_at"])

    attempt = _create_or_update_attempt(event, payment_link, config, normalized)

    from django.db import transaction as txn
    charge_id = normalized.charge_id or ""
    txn.on_commit(lambda: queue_payment_refunded(
        seller=payment_link.seller, payment_link=payment_link,
        dedup_suffix=charge_id,
    ))
    txn.on_commit(lambda: queue_payment_status_push(
        payment_link=payment_link, event_type="payment_refunded", dedup_suffix=charge_id,
    ))

    logger.info("Link %s marcado como REFUNDED, attempt=%s", payment_link.id, attempt.id)


def _handle_mark_expired(event, payment_link, config, normalized):
    if payment_link.status in FINAL_STATES:
        event.processing_status = ProcessingStatus.IGNORED
        event.processed_at = timezone.now()
        event.save(update_fields=["processing_status", "processed_at"])
        return

    payment_link.status = PaymentLinkStatus.EXPIRED
    payment_link.save(update_fields=["status", "updated_at"])

    from django.db import transaction as txn
    txn.on_commit(lambda: queue_payment_expired(
        seller=payment_link.seller, payment_link=payment_link,
    ))
    txn.on_commit(lambda: queue_payment_status_push(
        payment_link=payment_link, event_type="payment_expired",
    ))

    logger.info("Link %s marcado como EXPIRADO", payment_link.id)


def _handle_ignore_if_final(event, payment_link, config, normalized):
    """Ignore event if link is already in a final state, otherwise process."""
    if payment_link.status in FINAL_STATES:
        event.processing_status = ProcessingStatus.IGNORED
        event.processed_at = timezone.now()
        event.save(update_fields=["processing_status", "processed_at"])
        return

    # Re-dispatch based on the real meaning
    if "closed" in event.event_type or "canceled" in event.event_type:
        _handle_mark_expired(event, payment_link, config, normalized)
    else:
        # Reprocess with create_attempt logic for other ignore_if_final events
        # that reached here (link not final)
        _handle_create_attempt(event, payment_link, config, normalized)


ACTION_HANDLERS = {
    "mark_paid": _handle_mark_paid,
    "create_attempt": _handle_create_attempt,
    "mark_canceled": _handle_mark_canceled,
    "mark_refunded": _handle_mark_refunded,
    "mark_expired": _handle_mark_expired,
    "ignore_if_final": _handle_ignore_if_final,
}


def _find_payment_link(event: WebhookEvent, normalized) -> PaymentLink | None:
    """Find payment link using normalized event data in priority order."""
    if normalized.internal_payment_link_id:
        try:
            return PaymentLink.objects.get(id=normalized.internal_payment_link_id)
        except (PaymentLink.DoesNotExist, ValueError):
            pass

    if normalized.payment_link_id:
        link = PaymentLink.objects.filter(provider_link_id=normalized.payment_link_id).first()
        if link:
            return link

    if normalized.checkout_id:
        link = PaymentLink.objects.filter(provider_link_id=normalized.checkout_id).first()
        if link:
            return link

    if normalized.order_id:
        link = PaymentLink.objects.filter(provider_link_id=normalized.order_id).first()
        if link:
            return link

    if normalized.order_code:
        candidates = list(
            PaymentLink.objects.filter(reference=normalized.order_code, provider="pagarme")[:2]
        )
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            logger.error(
                "Referência ambígua no webhook: event=%s reference=%s",
                event.id,
                normalized.order_code,
            )

    return None


def _create_or_update_attempt(event, payment_link, config, normalized) -> PaymentAttempt:
    """Create or update payment attempt using normalized data."""
    attempt_status = config["attempt_status"]

    attempt = None
    if normalized.order_id:
        attempt = PaymentAttempt.objects.filter(
            payment_link=payment_link, provider_order_id=normalized.order_id,
        ).first()
    if attempt is None and normalized.charge_id:
        attempt = PaymentAttempt.objects.filter(
            payment_link=payment_link, provider_charge_id=normalized.charge_id,
        ).first()

    amount = normalized.amount_cents or payment_link.amount_cents

    if attempt:
        attempt.status = attempt_status
        if normalized.transaction_id:
            attempt.raw_summary = _sanitize_summary(event.payload.get("data", {}))
        if attempt_status == "PAID" and not attempt.paid_at:
            attempt.paid_at = timezone.now()
        if normalized.failure.raw_code:
            attempt.failure_code = normalized.failure.raw_code
        if normalized.failure.raw_message:
            attempt.failure_message = normalized.failure.raw_message[:255]
        attempt.save()
    else:
        attempt = PaymentAttempt.objects.create(
            payment_link=payment_link,
            provider_order_id=normalized.order_id or "",
            provider_charge_id=normalized.charge_id or "",
            status=attempt_status,
            amount_cents=amount,
            installments=normalized.installments,
            failure_code=normalized.failure.raw_code or "",
            failure_message=normalized.failure.raw_message[:255] if normalized.failure.raw_message else "",
            paid_at=timezone.now() if attempt_status == "PAID" else None,
            raw_summary=_sanitize_summary(event.payload.get("data", {})),
        )

    return attempt


def _sanitize_summary(data: dict) -> dict:
    summary = {
        "id": data.get("id"),
        "status": data.get("status"),
        "amount": data.get("amount"),
        "currency": data.get("currency"),
    }
    charges = data.get("charges", [])
    if charges:
        charge = charges[0]
        summary["charge_status"] = charge.get("status")
        summary["payment_method"] = charge.get("payment_method")
        last_transaction = charge.get("last_transaction", {})
        if last_transaction:
            summary["transaction_status"] = last_transaction.get("status")
            summary["installments"] = last_transaction.get("installments")
    return summary
