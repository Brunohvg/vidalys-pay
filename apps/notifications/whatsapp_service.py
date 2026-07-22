"""WhatsApp sending service — outbox pattern for reliable delivery."""
import logging

from django.db import transaction

from apps.sellers.models import Seller

from .models import NotificationOutbox, WhatsAppMessage, WhatsAppMessageStatus
from .templates_msg import (
    invitation_message,
    payment_approved_message,
    payment_canceled_message,
    payment_expired_message,
    payment_failed_message,
    payment_link_created_message,
    payment_refunded_message,
)

logger = logging.getLogger("apps.notifications")


def queue_invitation(*, seller: Seller, activation_url: str) -> WhatsAppMessage:
    """Queue invitation message for a seller."""
    text = invitation_message(
        seller_name=seller.name,
        activation_url=activation_url,
    )

    return _queue_message(
        seller=seller,
        template_key="invitation",
        text=text,
        topic="whatsapp.send",
        aggregate_type="seller",
        aggregate_id=seller.id,
    )


def queue_payment_link_created(
    *,
    seller: Seller,
    payment_link,
) -> WhatsAppMessage:
    """Queue payment link created message."""
    text = payment_link_created_message(
        reference=payment_link.reference,
        customer_name=payment_link.customer_name or None,
        amount_cents=payment_link.amount_cents,
        installments=payment_link.installments,
        payment_url=payment_link.payment_url,
    )

    return _queue_message(
        seller=seller,
        template_key="payment_link_created",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
    )


def queue_payment_approved(
    *,
    seller: Seller,
    payment_link,
) -> WhatsAppMessage:
    """Queue payment approved message."""
    text = payment_approved_message(
        reference=payment_link.reference,
        amount_cents=payment_link.amount_cents,
        customer_name=payment_link.customer_name or None,
    )

    return _queue_message(
        seller=seller,
        template_key="payment_approved",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
    )


def queue_payment_failed(
    *,
    seller: Seller,
    payment_link,
) -> WhatsAppMessage:
    """Queue payment failed message."""
    text = payment_failed_message(
        reference=payment_link.reference,
        amount_cents=payment_link.amount_cents,
    )

    return _queue_message(
        seller=seller,
        template_key="payment_failed",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
    )


def queue_payment_expired(*, seller: Seller, payment_link) -> WhatsAppMessage:
    """Queue payment expired message."""
    text = payment_expired_message(reference=payment_link.reference)

    return _queue_message(
        seller=seller,
        template_key="payment_expired",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
    )


def queue_payment_canceled(*, seller: Seller, payment_link) -> WhatsAppMessage:
    """Queue payment canceled message."""
    text = payment_canceled_message(reference=payment_link.reference)

    return _queue_message(
        seller=seller,
        template_key="payment_canceled",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
    )


def queue_payment_refunded(*, seller: Seller, payment_link) -> WhatsAppMessage:
    """Queue payment refunded message."""
    text = payment_refunded_message(
        reference=payment_link.reference,
        amount_cents=payment_link.amount_cents,
    )

    return _queue_message(
        seller=seller,
        template_key="payment_refunded",
        text=text,
        topic="whatsapp.send",
        aggregate_type="payment_link",
        aggregate_id=payment_link.id,
        payment_link=payment_link,
    )


def _queue_message(
    *,
    seller: Seller,
    template_key: str,
    text: str,
    topic: str,
    aggregate_type: str,
    aggregate_id,
    payment_link=None,
) -> WhatsAppMessage:
    """Create outbox entry and WhatsApp message record."""
    # Deduplication key: prevent duplicate messages for same aggregate + template
    dedup_key = f"{aggregate_type}:{aggregate_id}:{template_key}"

    with transaction.atomic():
        existing = NotificationOutbox.objects.filter(
            deduplication_key=dedup_key,
            status__in=["PENDING", "PROCESSING"],
        ).first()

        if existing:
            logger.info("Mensagem duplicada ignorada: %s", dedup_key)
            return WhatsAppMessage.objects.filter(
                seller=seller,
                template_key=template_key,
                payment_link=payment_link,
            ).order_by("-created_at").first()

        NotificationOutbox.objects.filter(deduplication_key=dedup_key).delete()

        message = WhatsAppMessage.objects.create(
            seller=seller,
            payment_link=payment_link,
            template_key=template_key,
            recipient_phone=seller.whatsapp_phone,
            rendered_text=text,
            status=WhatsAppMessageStatus.QUEUED,
        )

        # Create outbox entry
        NotificationOutbox.objects.create(
            topic=topic,
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id),
            deduplication_key=dedup_key,
            payload={
                "message_id": str(message.id),
                "phone": seller.whatsapp_phone,
                "text": text,
            },
            status="PENDING",
        )

    logger.info(
        "Mensagem enfileirada: %s para %s",
        template_key,
        seller.whatsapp_phone,
    )
    return message
