"""Web Push subscriptions and delivery service."""
import json
import logging

from django.conf import settings

from apps.payment_links.models import PaymentLink

from .models import NotificationOutbox, PushSubscription

logger = logging.getLogger("apps.notifications.push")

EVENT_CONTENT = {
    "payment_paid": ("Pagamento aprovado", "O link {reference} foi pago: {amount}."),
    "payment_failed": ("Pagamento não aprovado", "A tentativa no link {reference} não foi concluída."),
    "payment_canceled": ("Link cancelado", "O link {reference} foi cancelado."),
    "payment_expired": ("Link expirado", "O link {reference} expirou."),
    "payment_refunded": ("Pagamento reembolsado", "O pagamento de {amount} do link {reference} foi reembolsado."),
    "payment_chargedback": ("Chargeback recebido", "O pagamento do link {reference} recebeu um chargeback."),
}


def queue_payment_status_push(*, payment_link: PaymentLink, event_type: str, dedup_suffix: str = "") -> bool:
    """Queue one push event per link status without performing network I/O."""
    content = EVENT_CONTENT.get(event_type)
    if not content or not settings.WEBPUSH_VAPID_PRIVATE_KEY:
        return False
    title, body_template = content
    amount = _format_brl(payment_link.amount_cents)
    body = body_template.format(reference=payment_link.reference, amount=amount)
    suffix = f":{dedup_suffix}" if dedup_suffix else ""
    dedup_key = f"webpush:payment_link:{payment_link.id}:{event_type}{suffix}"
    _, created = NotificationOutbox.objects.get_or_create(
        deduplication_key=dedup_key,
        defaults={
            "topic": "webpush.send",
            "aggregate_type": "payment_link",
            "aggregate_id": payment_link.id,
            "payload": {
                "seller_id": str(payment_link.seller_id),
                "title": title,
                "body": body,
                "event_type": event_type,
                "url": f"/app/historico/?highlight={payment_link.id}",
                "tag": f"payment-link-{payment_link.id}",
                "badge": "/static/pwa/app-icon-192.png",
                "icon": "/static/pwa/app-icon-192.png",
            },
            "status": "PENDING",
        },
    )
    return created


def send_push_outbox_item(item) -> bool:
    """Send an outbox payload to every active device for the seller."""
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.error("pywebpush não está instalado")
        return False

    subscriptions = PushSubscription.objects.filter(
        seller_id=item.payload.get("seller_id"),
        is_active=True,
    ).exclude(last_delivery_key=item.deduplication_key)
    transient_failure = False
    payload = json.dumps(item.payload, ensure_ascii=False)

    for subscription in subscriptions.iterator():
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=settings.WEBPUSH_VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.WEBPUSH_VAPID_SUBJECT},
                ttl=86400,
            )
            subscription.last_delivery_key = item.deduplication_key
            subscription.failure_count = 0
            subscription.save(update_fields=["last_delivery_key", "failure_count", "updated_at"])
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in (404, 410):
                subscription.is_active = False
                subscription.save(update_fields=["is_active", "updated_at"])
                logger.info("Assinatura push expirada desativada: %s", subscription.id)
            else:
                subscription.failure_count += 1
                if subscription.failure_count >= 5:
                    subscription.is_active = False
                subscription.save(update_fields=["failure_count", "is_active", "updated_at"])
                transient_failure = True
                logger.warning("Falha Web Push assinatura=%s status=%s", subscription.id, status_code)
        except Exception:
            logger.exception("Erro inesperado no Web Push assinatura=%s", subscription.id)
            transient_failure = True

    return not transient_failure


def _format_brl(cents: int) -> str:
    value = cents / 100
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

