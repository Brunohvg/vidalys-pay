"""Web Push subscriptions and delivery service."""
import json
import logging

from django.conf import settings

from apps.boletos.models import Boleto
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

BOLETO_EVENT_CONTENT = {
    "boleto_created": ("Boleto emitido", "Boleto de {company} emitido no valor de {amount}."),
    "boleto_paid": ("Boleto pago", "Pagamento de {company} confirmado: {amount}."),
    "boleto_failed": ("Falha no boleto", "A cobrança de {company} não foi concluída."),
    "boleto_expired": ("Boleto vencido", "O boleto de {company}, no valor de {amount}, venceu."),
    "boleto_canceled": ("Boleto cancelado", "O boleto de {company} foi cancelado."),
    "boleto_partially_canceled": ("Boleto parcialmente cancelado", "O boleto de {company} foi parcialmente cancelado."),
    "boleto_refunded": ("Boleto estornado", "O pagamento de {company}, no valor de {amount}, foi estornado."),
}

DELIVERED_SUBSCRIPTIONS_KEY = "_delivered_subscription_ids"


def queue_payment_status_push(*, payment_link: PaymentLink, event_type: str, dedup_suffix: str = "") -> bool:
    """Queue one push event per link status without performing network I/O."""
    content = EVENT_CONTENT.get(event_type)
    if not content or not (
        settings.WEBPUSH_VAPID_PUBLIC_KEY and settings.WEBPUSH_VAPID_PRIVATE_KEY
    ):
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


def queue_boleto_status_push(*, boleto: Boleto, event_type: str) -> bool:
    """Queue one idempotent push for a boleto lifecycle event."""
    content = BOLETO_EVENT_CONTENT.get(event_type)
    if not content:
        return False
    title, body_template = content
    company = boleto.company_snapshot.get("legal_name") or boleto.company.legal_name
    return _queue_boleto_push(
        boleto=boleto,
        event_type=event_type,
        title=title,
        body=body_template.format(company=company, amount=_format_brl(boleto.amount_cents)),
    )


def queue_boleto_reminder_push(*, boleto: Boleto, days_until_due: int) -> bool:
    """Queue one reminder push for a configured due-date offset."""
    title, body = _boleto_reminder_content(boleto, days_until_due)
    return _queue_boleto_push(
        boleto=boleto,
        event_type=_reminder_event_type(days_until_due),
        title=title,
        body=body,
    )


def _queue_boleto_push(*, boleto: Boleto, event_type: str, title: str, body: str) -> bool:
    if not (
        settings.WEBPUSH_VAPID_PUBLIC_KEY and settings.WEBPUSH_VAPID_PRIVATE_KEY
    ):
        return False
    dedup_key = f"webpush:boleto:{boleto.id}:{event_type}"
    _, created = NotificationOutbox.objects.get_or_create(
        deduplication_key=dedup_key,
        defaults={
            "topic": "webpush.send",
            "aggregate_type": "boleto",
            "aggregate_id": boleto.id,
            "payload": {
                "seller_id": str(boleto.seller_id),
                "title": title,
                "body": body,
                "event_type": event_type,
                "url": f"/app/boletos/{boleto.id}/",
                "tag": f"boleto-{boleto.id}-{event_type}",
                "badge": "/static/pwa/app-icon-192.png",
                "icon": "/static/pwa/app-icon-192.png",
            },
            "status": "PENDING",
        },
    )
    return created


def _boleto_reminder_content(boleto: Boleto, days_until_due: int) -> tuple[str, str]:
    company = boleto.company_snapshot.get("legal_name") or boleto.company.legal_name
    amount = _format_brl(boleto.amount_cents)
    if days_until_due > 0:
        title = "Boleto próximo do vencimento"
        timing = f"vence em {days_until_due} dia{'s' if days_until_due != 1 else ''}"
    elif days_until_due == 0:
        title = "Boleto vence hoje"
        timing = "vence hoje"
    else:
        title = "Boleto vencido"
        overdue_days = abs(days_until_due)
        timing = f"venceu há {overdue_days} dia{'s' if overdue_days != 1 else ''}"
    return title, f"O boleto de {company}, no valor de {amount}, {timing}."


def _reminder_event_type(days_until_due: int) -> str:
    suffix = f"minus_{abs(days_until_due)}" if days_until_due < 0 else str(days_until_due)
    return f"boleto_due_{suffix}"


def send_push_outbox_item(item) -> bool:
    """Send an outbox payload to every active device for the seller."""
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.error("pywebpush não está instalado")
        return False

    delivered_ids = set(item.payload.get(DELIVERED_SUBSCRIPTIONS_KEY, []))
    subscriptions = PushSubscription.objects.filter(
        seller_id=item.payload.get("seller_id"),
        is_active=True,
    ).exclude(id__in=delivered_ids)
    transient_failure = False
    public_payload = {
        key: value for key, value in item.payload.items() if not key.startswith("_")
    }
    payload = json.dumps(public_payload, ensure_ascii=False)

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
            delivered_ids.add(str(subscription.id))
            item.payload[DELIVERED_SUBSCRIPTIONS_KEY] = sorted(delivered_ids)
            item.save(update_fields=["payload"])
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
            subscription.failure_count += 1
            if subscription.failure_count >= 5:
                subscription.is_active = False
            subscription.save(update_fields=["failure_count", "is_active", "updated_at"])
            transient_failure = True

    return not transient_failure


def _format_brl(cents: int) -> str:
    value = cents / 100
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
