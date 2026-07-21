"""Webhook event processor — maps events to state transitions."""
import logging

from django.db import transaction
from django.utils import timezone

from apps.notifications.whatsapp_service import (
    queue_payment_approved,
    queue_payment_canceled,
    queue_payment_expired,
    queue_payment_failed,
)
from apps.payment_links.models import (
    PaymentAttempt,
    PaymentLink,
    PaymentLinkStatus,
)

from .event_mapping import can_transition, get_event_config, is_final_state
from .models import ProcessingStatus, WebhookEvent

logger = logging.getLogger("apps.webhooks")


def process_webhook_event(event: WebhookEvent) -> bool:
    """Process a webhook event.

    Returns True if processed successfully, False otherwise.
    """
    config = get_event_config(event.event_type)

    if config is None:
        logger.info("Evento desconhecido: %s — marcando como IGNORED", event.event_type)
        event.processing_status = ProcessingStatus.IGNORED
        event.processed_at = timezone.now()
        event.save(update_fields=["processing_status", "processed_at"])
        return True

    action = config.get("action", "ignore")

    if action == "ignore":
        event.processing_status = ProcessingStatus.IGNORED
        event.processed_at = timezone.now()
        event.save(update_fields=["processing_status", "processed_at"])
        return True

    if action == "ignore_if_final":
        return _handle_ignore_if_final(event)

    # Find the payment link
    payment_link = _find_payment_link(event)

    if payment_link is None:
        logger.warning("Link não encontrado para evento %s", event.event_type)
        event.processing_status = ProcessingStatus.IGNORED
        event.processed_at = timezone.now()
        event.save(update_fields=["processing_status", "processed_at"])
        return True

    try:
        with transaction.atomic():
            if action == "mark_paid":
                _mark_paid(event, payment_link, config)
            elif action == "create_attempt":
                _create_or_update_attempt(event, payment_link, config)
            elif action == "mark_canceled":
                _mark_canceled(event, payment_link, config)
            elif action == "mark_refunded":
                _mark_refunded(event, payment_link, config)
            else:
                logger.warning("Ação desconhecida: %s", action)
                event.processing_status = ProcessingStatus.IGNORED
                event.processed_at = timezone.now()
                event.save(update_fields=["processing_status", "processed_at"])
                return True

            event.processing_status = ProcessingStatus.PROCESSED
            event.processed_at = timezone.now()
            event.save(update_fields=["processing_status", "processed_at"])

        return True

    except Exception as e:
        logger.exception("Erro ao processar evento %s: %s", event.event_type, e)
        event.processing_status = ProcessingStatus.FAILED
        event.error_code = "PROCESSING_ERROR"
        event.error_detail = str(e)[:255]
        event.save(update_fields=["processing_status", "error_code", "error_detail"])
        return False


def _find_payment_link(event: WebhookEvent) -> PaymentLink | None:
    """Find payment link from event payload."""
    data = event.payload.get("data", {})

    # Try to find by metadata.internal_payment_link_id
    metadata = data.get("metadata", {})
    internal_id = metadata.get("internal_payment_link_id")
    if internal_id:
        try:
            return PaymentLink.objects.get(id=internal_id)
        except (PaymentLink.DoesNotExist, ValueError):
            pass

    # Try to find by order code (reference)
    order_code = data.get("code", "")
    if order_code:
        link = PaymentLink.objects.filter(
            reference=order_code,
            provider="pagarme",
        ).first()
        if link:
            return link

    # Try to find by provider_link_id
    checkout_id = data.get("checkout", {}).get("id", "")
    if checkout_id:
        link = PaymentLink.objects.filter(
            provider_link_id=checkout_id,
        ).first()
        if link:
            return link

    # Try to find by order id in provider_link_id
    order_id = data.get("id", "")
    if order_id:
        link = PaymentLink.objects.filter(
            provider_link_id=order_id,
        ).first()
        if link:
            return link

    return None


def _mark_paid(event: WebhookEvent, payment_link: PaymentLink, config: dict):
    """Mark payment link as paid."""
    if not can_transition(payment_link.status, config["link_status"]):
        logger.info(
            "Transição não permitida: %s → %s para link %s",
            payment_link.status,
            config["link_status"],
            payment_link.id,
        )
        return

    data = event.payload.get("data", {})

    payment_link.status = PaymentLinkStatus.PAID
    payment_link.paid_at = timezone.now()
    payment_link.provider_status = data.get("status", "paid")
    payment_link.save(update_fields=["status", "paid_at", "provider_status", "updated_at"])

    # Create or update attempt
    _create_or_update_attempt(event, payment_link, config)

    # Queue notification
    _queue_notification(
        template_key="payment_approved",
        payment_link=payment_link,
        seller=payment_link.seller,
    )

    logger.info("Link %s marcado como PAGO", payment_link.id)


def _mark_canceled(event: WebhookEvent, payment_link: PaymentLink, config: dict):
    """Mark payment link as canceled."""
    if not can_transition(payment_link.status, config["link_status"]):
        logger.info(
            "Transição não permitida: %s → %s para link %s",
            payment_link.status,
            config["link_status"],
            payment_link.id,
        )
        return

    data = event.payload.get("data", {})

    payment_link.status = PaymentLinkStatus.CANCELED
    payment_link.canceled_at = timezone.now()
    payment_link.provider_status = data.get("status", "canceled")
    payment_link.save(update_fields=["status", "canceled_at", "provider_status", "updated_at"])

    # Queue notification
    _queue_notification(
        template_key="payment_canceled",
        payment_link=payment_link,
        seller=payment_link.seller,
    )

    logger.info("Link %s marcado como CANCELADO", payment_link.id)


def _mark_refunded(event: WebhookEvent, payment_link: PaymentLink, config: dict):
    """Mark payment link as refunded."""
    if not can_transition(payment_link.status, config["link_status"]):
        logger.info(
            "Transição não permitida: %s → %s para link %s",
            payment_link.status,
            config["link_status"],
            payment_link.id,
        )
        return

    payment_link.status = PaymentLinkStatus.REFUNDED
    payment_link.refunded_at = timezone.now()
    payment_link.save(update_fields=["status", "refunded_at", "updated_at"])

    # Update attempt
    _create_or_update_attempt(event, payment_link, config)

    logger.info("Link %s marcado como REEMBOLSADO", payment_link.id)


def _create_or_update_attempt(event: WebhookEvent, payment_link: PaymentLink, config: dict):
    """Create or update payment attempt from event."""
    data = event.payload.get("data", {})
    attempt_status = config["attempt_status"]

    # Extract charge info
    charges = data.get("charges", [])
    charge = charges[0] if charges else {}

    provider_order_id = data.get("id", "")
    provider_charge_id = charge.get("id", "")
    amount_cents = charge.get("amount", data.get("amount", 0))

    # Extract transaction info
    last_transaction = charge.get("last_transaction", {})
    installments = last_transaction.get("installments")
    failure_code = last_transaction.get("gateway_response", {}).get("code", "")
    failure_message = last_transaction.get("gateway_response", {}).get("message", "")

    # Try to find existing attempt
    attempt = None
    if provider_order_id:
        attempt = PaymentAttempt.objects.filter(
            payment_link=payment_link,
            provider_order_id=provider_order_id,
        ).first()

    if attempt is None and provider_charge_id:
        attempt = PaymentAttempt.objects.filter(
            payment_link=payment_link,
            provider_charge_id=provider_charge_id,
        ).first()

    if attempt:
        # Update existing attempt
        attempt.status = attempt_status
        if attempt_status == "PAID":
            attempt.paid_at = timezone.now()
        if failure_code:
            attempt.failure_code = failure_code
        if failure_message:
            attempt.failure_message = failure_message[:255]
        attempt.raw_summary = _sanitize_summary(data)
        attempt.save()
    else:
        # Create new attempt
        attempt = PaymentAttempt.objects.create(
            payment_link=payment_link,
            provider_order_id=provider_order_id,
            provider_charge_id=provider_charge_id,
            status=attempt_status,
            amount_cents=amount_cents,
            installments=installments,
            failure_code=failure_code,
            failure_message=failure_message[:255] if failure_message else "",
            paid_at=timezone.now() if attempt_status == "PAID" else None,
            raw_summary=_sanitize_summary(data),
        )

    # Queue notification on failure
    if attempt_status == "FAILED":
        _queue_notification(
            template_key="payment_failed",
            payment_link=payment_link,
            seller=payment_link.seller,
        )

    return attempt


def _handle_ignore_if_final(event: WebhookEvent) -> bool:
    """Handle events that should be ignored if link is in final state."""
    payment_link = _find_payment_link(event)

    if payment_link and is_final_state(payment_link.status):
        event.processing_status = ProcessingStatus.IGNORED
        event.processed_at = timezone.now()
        event.save(update_fields=["processing_status", "processed_at"])
        return True

    # Otherwise process normally
    return process_webhook_event(event)


def _sanitize_summary(data: dict) -> dict:
    """Sanitize data for storage — remove sensitive fields."""
    summary = {
        "id": data.get("id"),
        "status": data.get("status"),
        "amount": data.get("amount"),
        "currency": data.get("currency"),
    }
    # Include charge info without card details
    charges = data.get("charges", [])
    if charges:
        charge = charges[0]
        summary["charge_status"] = charge.get("status")
        summary["payment_method"] = charge.get("payment_method")
        # Include transaction without card data
        last_transaction = charge.get("last_transaction", {})
        if last_transaction:
            summary["transaction_status"] = last_transaction.get("status")
            summary["installments"] = last_transaction.get("installments")
            summary["acquirer_name"] = last_transaction.get("acquirer_name")
    return summary


def _queue_notification(*, template_key: str, payment_link, seller):
    """Queue WhatsApp notification."""
    try:
        if template_key == "payment_approved":
            queue_payment_approved(seller=seller, payment_link=payment_link)
        elif template_key == "payment_failed":
            queue_payment_failed(seller=seller, payment_link=payment_link)
        elif template_key == "payment_canceled":
            queue_payment_canceled(seller=seller, payment_link=payment_link)
        elif template_key == "payment_expired":
            queue_payment_expired(seller=seller, payment_link=payment_link)
    except Exception:
        logger.exception("Erro ao enfileirar notificação %s", template_key)
