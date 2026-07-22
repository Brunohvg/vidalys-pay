"""WhatsApp sending service — outbox pattern for reliable delivery."""
import logging
from dataclasses import dataclass

from django.db import transaction

from apps.sellers.models import Seller

from .models import NotificationOutbox, RecipientType, WhatsAppMessage, WhatsAppMessageStatus
from .templates_msg import (
    invitation_message,
    payment_approved_message,
    payment_canceled_message,
    payment_chargedback_message,
    payment_expired_message,
    payment_failed_message,
    payment_link_created_message,
    payment_refunded_message,
)

logger = logging.getLogger("apps.notifications")


@dataclass
class WhatsAppDeliveryResult:
    """Result of queuing a WhatsApp delivery."""

    status: str  # queued, not_requested, duplicate
    message_id: str | None = None
    recipient_type: str = ""
    recipient_phone: str = ""


def queue_invitation(*, seller: Seller, activation_url: str) -> WhatsAppMessage:
    """Queue invitation message for a seller."""
    text = invitation_message(
        seller_name=seller.name,
        activation_url=activation_url,
    )

    return _queue_message(
        seller=seller,
        template_key="invitation",
        event_type="invitation",
        text=text,
        topic="whatsapp.send",
        aggregate_type="seller",
        aggregate_id=seller.id,
        recipient_phone=seller.whatsapp_phone,
        recipient_type=RecipientType.SELLER,
    )


def queue_payment_link_created(
    *,
    seller: Seller,
    payment_link,
) -> list[WhatsAppDeliveryResult]:
    """Queue payment link created message to seller and optionally customer.

    Returns a list of delivery results for each recipient.
    """
    results = []
    customer_phone = getattr(payment_link, "customer_phone", None) or None

    # 1. Always queue for seller
    text = payment_link_created_message(
        reference=payment_link.reference,
        customer_name=payment_link.customer_name or None,
        amount_cents=payment_link.amount_cents,
        installments=payment_link.installments,
        payment_url=payment_link.payment_url,
    )

    if seller.whatsapp_phone:
        message = _queue_message(
            seller=seller,
            template_key="payment_link_created",
            event_type="payment_link_created",
            text=text,
            topic="whatsapp.send",
            aggregate_type="payment_link",
            aggregate_id=payment_link.id,
            payment_link=payment_link,
            recipient_phone=seller.whatsapp_phone,
            recipient_type=RecipientType.SELLER,
        )
        results.append(WhatsAppDeliveryResult(
            status="queued" if message else "duplicate",
            message_id=str(message.id) if message else None,
            recipient_type=RecipientType.SELLER,
            recipient_phone=seller.whatsapp_phone,
        ))
    else:
        results.append(WhatsAppDeliveryResult(
            status="failed",
            recipient_type=RecipientType.SELLER,
            recipient_phone="",
        ))

    # 2. Optionally queue for customer
    if customer_phone:
        customer_text = payment_link_created_message(
            reference=payment_link.reference,
            customer_name=payment_link.customer_name or None,
            amount_cents=payment_link.amount_cents,
            installments=payment_link.installments,
            payment_url=payment_link.payment_url,
        )

        message = _queue_message(
            seller=seller,
            template_key="payment_link_created_customer",
            event_type="payment_link_created",
            text=customer_text,
            topic="whatsapp.send",
            aggregate_type="payment_link",
            aggregate_id=payment_link.id,
            payment_link=payment_link,
            recipient_phone=customer_phone,
            recipient_type=RecipientType.CUSTOMER,
        )
        results.append(WhatsAppDeliveryResult(
            status="queued" if message else "duplicate",
            message_id=str(message.id) if message else None,
            recipient_type=RecipientType.CUSTOMER,
            recipient_phone=customer_phone,
        ))
    else:
        results.append(WhatsAppDeliveryResult(
            status="not_requested",
            recipient_type=RecipientType.CUSTOMER,
            recipient_phone="",
        ))

    return results


def queue_payment_approved(
    *,
    seller: Seller,
    payment_link,
) -> WhatsAppMessage:
    text = payment_approved_message(
        reference=payment_link.reference,
        amount_cents=payment_link.amount_cents,
        customer_name=payment_link.customer_name or None,
    )

    return _queue_message(
        seller=seller,
        template_key="payment_approved",
        event_type="payment_approved",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
        recipient_phone=seller.whatsapp_phone,
        recipient_type=RecipientType.SELLER,
    )


def queue_payment_failed(
    *,
    seller: Seller,
    payment_link,
    failure_reason: str = "",
    dedup_suffix: str = "",
) -> WhatsAppMessage:
    text = payment_failed_message(
        reference=payment_link.reference,
        amount_cents=payment_link.amount_cents,
        failure_reason=failure_reason,
    )

    dedup_key_suffix = f":{dedup_suffix}" if dedup_suffix else ""

    return _queue_message(
        seller=seller,
        template_key=f"payment_failed{dedup_key_suffix}",
        event_type="payment_failed",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
        recipient_phone=seller.whatsapp_phone,
        recipient_type=RecipientType.SELLER,
    )


def queue_payment_expired(*, seller: Seller, payment_link) -> WhatsAppMessage:
    """Queue payment expired message."""
    text = payment_expired_message(reference=payment_link.reference)

    return _queue_message(
        seller=seller,
        template_key="payment_expired",
        event_type="payment_expired",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
        recipient_phone=seller.whatsapp_phone,
        recipient_type=RecipientType.SELLER,
    )


def queue_payment_canceled(*, seller: Seller, payment_link) -> WhatsAppMessage:
    """Queue payment canceled message."""
    text = payment_canceled_message(reference=payment_link.reference)

    return _queue_message(
        seller=seller,
        template_key="payment_canceled",
        event_type="payment_canceled",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
        recipient_phone=seller.whatsapp_phone,
        recipient_type=RecipientType.SELLER,
    )


def queue_payment_refunded(
    *,
    seller: Seller,
    payment_link,
    dedup_suffix: str = "",
) -> WhatsAppMessage:
    text = payment_refunded_message(
        reference=payment_link.reference,
        amount_cents=payment_link.amount_cents,
    )

    dedup_key_suffix = f":{dedup_suffix}" if dedup_suffix else ""

    return _queue_message(
        seller=seller,
        template_key=f"payment_refunded{dedup_key_suffix}",
        event_type="payment_refunded",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
        recipient_phone=seller.whatsapp_phone,
        recipient_type=RecipientType.SELLER,
    )


def queue_payment_chargedback(
    *,
    seller: Seller,
    payment_link,
    dedup_suffix: str = "",
) -> WhatsAppMessage:
    text = payment_chargedback_message(
        reference=payment_link.reference,
        amount_cents=payment_link.amount_cents,
    )

    dedup_key_suffix = f":{dedup_suffix}" if dedup_suffix else ""

    return _queue_message(
        seller=seller,
        template_key=f"payment_chargedback{dedup_key_suffix}",
        event_type="payment_chargedback",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
        recipient_phone=seller.whatsapp_phone,
        recipient_type=RecipientType.SELLER,
    )


def _queue_message(
    *,
    seller: Seller,
    template_key: str,
    event_type: str,
    text: str,
    topic: str,
    aggregate_type: str,
    aggregate_id,
    payment_link=None,
    recipient_phone: str,
    recipient_type: str,
) -> WhatsAppMessage | None:
    """Create outbox entry and WhatsApp message record.

    Deduplication key includes: aggregate + event + recipient_type + phone.
    Returns None if a duplicate pending/processing message already exists.
    """
    dedup_key = f"{aggregate_type}:{aggregate_id}:{event_type}:{recipient_type}:{recipient_phone}"

    with transaction.atomic():
        existing = NotificationOutbox.objects.filter(
            deduplication_key=dedup_key,
            status__in=["PENDING", "PROCESSING"],
        ).first()

        if existing:
            logger.info("Mensagem duplicada ignorada: %s", dedup_key)
            return None

        NotificationOutbox.objects.filter(deduplication_key=dedup_key).delete()

        message = WhatsAppMessage.objects.create(
            seller=seller,
            payment_link=payment_link,
            template_key=template_key,
            event_type=event_type,
            recipient_type=recipient_type,
            recipient_phone=recipient_phone,
            rendered_text=text,
            status=WhatsAppMessageStatus.QUEUED,
        )

        NotificationOutbox.objects.create(
            topic=topic,
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id),
            deduplication_key=dedup_key,
            payload={
                "message_id": str(message.id),
                "phone": recipient_phone,
                "text": text,
            },
            status="PENDING",
        )

    logger.info(
        "Mensagem enfileirada: %s → %s:%s",
        template_key,
        recipient_type,
        recipient_phone,
    )
    return message
