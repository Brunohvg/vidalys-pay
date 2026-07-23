"""WhatsApp sending service — outbox pattern for reliable delivery."""
import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from apps.sellers.models import Selle

from .models import NotificationOutbox, RecipientType, WhatsAppMessage, WhatsAppMessageStatus
from .templates_msg import (
    boleto_created_customer_message,
    boleto_created_seller_message,
    boleto_status_message,
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

    # 1. Always queue for selle
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

    # 2. Optionally queue for custome
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
    boleto=None,
    recipient_phone: str,
    recipient_type: str,
    deduplicate_forever: bool = False,
) -> WhatsAppMessage | None:
    """Create outbox entry and WhatsApp message record.

    Deduplication key includes: aggregate + event + recipient_type + phone.
    Returns None if a duplicate pending/processing message already exists.
    """
    dedup_key = f"{aggregate_type}:{aggregate_id}:{event_type}:{recipient_type}:{recipient_phone}"

    with transaction.atomic():
        existing_query = NotificationOutbox.objects.filter(deduplication_key=dedup_key)
        existing = (
            existing_query.first()
            if deduplicate_foreve
            else existing_query.filter(status__in=["PENDING", "PROCESSING"]).first()
        )

        if existing:
            logger.info("Mensagem duplicada ignorada: %s", dedup_key)
            return None

        NotificationOutbox.objects.filter(deduplication_key=dedup_key).delete()

        message = WhatsAppMessage.objects.create(
            seller=seller,
            payment_link=payment_link,
            boleto=boleto,
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


def queue_boleto_created(*, boleto) -> list[WhatsAppDeliveryResult]:
    """Queue the creation notice for seller and, when available, customer."""
    deliveries = []
    recipients = [
        (
            RecipientType.SELLER,
            boleto.seller.whatsapp_phone,
            "boleto_created_seller",
            boleto_created_seller_message(boleto=boleto),
        ),
    ]
    recipients.append(
        (
            RecipientType.CUSTOMER,
            _boleto_customer_phone(boleto),
            "boleto_created_customer",
            boleto_created_customer_message(boleto=boleto),
        )
    )

    for recipient_type, phone, template_key, text in recipients:
        phone_status, normalized_phone = _phone_status(phone)
        if phone_status != "queued":
            deliveries.append(
                WhatsAppDeliveryResult(
                    status=phone_status,
                    recipient_type=recipient_type,
                    recipient_phone="",
                )
            )
            continue
        message = _queue_message(
            seller=boleto.seller,
            boleto=boleto,
            template_key=template_key,
            event_type="boleto_created",
            text=text,
            topic="whatsapp.send",
            aggregate_type="boleto",
            aggregate_id=boleto.id,
            recipient_phone=normalized_phone,
            recipient_type=recipient_type,
            deduplicate_forever=True,
        )
        deliveries.append(
            WhatsAppDeliveryResult(
                status="queued" if message else "duplicate",
                message_id=str(message.id) if message else None,
                recipient_type=recipient_type,
                recipient_phone=normalized_phone,
            )
        )
    return deliveries


def queue_boleto_status(*, boleto, event_type: str) -> list[WhatsAppDeliveryResult]:
    """Queue one deduplicated status notice for each configured recipient."""
    text = boleto_status_message(boleto=boleto, event_type=event_type)
    recipients = [(RecipientType.SELLER, boleto.seller.whatsapp_phone)]

    if event_type == "boleto_paid" and settings.BOLETO_NOTIFY_CUSTOMER_ON_PAID:
        customer_phone = _boleto_customer_phone(boleto)
        recipients.append((RecipientType.CUSTOMER, customer_phone))
    if event_type == "boleto_canceled" and settings.BOLETO_NOTIFY_CUSTOMER_ON_CANCELED:
        customer_phone = _boleto_customer_phone(boleto)
        recipients.append((RecipientType.CUSTOMER, customer_phone))
    if event_type in {"boleto_paid", "boleto_canceled"}:
        recipients.extend(
            (RecipientType.MANAGER, phone)
            for phone in settings.BOLETO_MANAGER_WHATSAPP_PHONES
            if phone
        )

    deliveries = []
    for recipient_type, phone in recipients:
        phone_status, normalized_phone = _phone_status(phone)
        if phone_status != "queued":
            deliveries.append(
                WhatsAppDeliveryResult(
                    status=phone_status,
                    recipient_type=recipient_type,
                    recipient_phone="",
                )
            )
            continue
        message = _queue_message(
            seller=boleto.seller,
            boleto=boleto,
            template_key=event_type,
            event_type=event_type,
            text=text,
            topic="whatsapp.send",
            aggregate_type="boleto",
            aggregate_id=boleto.id,
            recipient_phone=normalized_phone,
            recipient_type=recipient_type,
            deduplicate_forever=True,
        )
        deliveries.append(
            WhatsAppDeliveryResult(
                status="queued" if message else "duplicate",
                message_id=str(message.id) if message else None,
                recipient_type=recipient_type,
                recipient_phone=normalized_phone,
            )
        )
    return deliveries


def _boleto_customer_phone(boleto) -> str:
    snapshot = boleto.company_snapshot
    return snapshot.get("whatsapp_phone") or snapshot.get("phone") or ""


def _normalize_whatsapp_phone(phone: str) -> str:
    digits = "".join(character for character in str(phone or "") if character.isdigit())
    if digits.startswith("55") and len(digits) in {12, 13}:
        digits = digits[2:]
    if len(digits) not in {10, 11}:
        return ""
    if digits[0] == "0" or digits[1] == "0" or set(digits) == {"0"}:
        return ""
    if len(digits) == 11 and digits[2] != "9":
        return ""
    return f"55{digits}"


def _phone_status(phone: str) -> tuple[str, str]:
    if not str(phone or "").strip():
        return "missing_phone", ""
    normalized = _normalize_whatsapp_phone(phone)
    if not normalized:
        return "invalid_phone", ""
    return "queued", normalized
