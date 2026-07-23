"""Pagar.me webhook reconciliation tests for boletos."""

import base64
import json
from datetime import date
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.boletos.models import Boleto, BoletoStatus, Company
from apps.boletos.services.webhook_processing import ALLOWED_TRANSITIONS
from apps.notifications.models import NotificationOutbox, WhatsAppMessage
from apps.sellers.models import Selle
from apps.webhooks.models import ProcessingStatus, WebhookEvent
from apps.webhooks.pagarme_payload import normalize_event
from apps.webhooks.processor import process_webhook_event


@pytest.fixture
def boleto(db):
    seller = Seller.objects.create(
        name="Vendedor Webhook",
        whatsapp_phone="+5511999999999",
        max_payment_amount_cents=1_000_000,
    )
    company = Company.objects.create(
        cnpj="11222333000181",
        legal_name="EMPRESA WEBHOOK LTDA",
        zip_code="01310100",
        street="Avenida Paulista",
        number="1000",
        district="Bela Vista",
        city="São Paulo",
        state="SP",
    )
    return Boleto.objects.create(
        seller=seller,
        company=company,
        created_by_seller=seller,
        amount_cents=25_000,
        due_date=date(2026, 8, 10),
        description="Cobrança webhook",
        status=BoletoStatus.PENDING,
        idempotency_key="webhook-test",
        provider_order_id="or_boleto_1",
        provider_charge_id="ch_boleto_1",
        provider_transaction_id="tran_boleto_1",
        company_snapshot={"cnpj": company.cnpj},
    )


def _payload(boleto, event_type, *, event_id=None, status=None, metadata=True):
    resource = event_type.split(".", 1)[0]
    data = {
        "id": "or_boleto_1" if resource == "order" else "ch_boleto_1",
        "status": status or event_type.split(".", 1)[1],
        "order": {"id": "or_boleto_1"},
        "charges": [
            {
                "id": "ch_boleto_1",
                "last_transaction": {"id": "tran_boleto_1"},
            }
        ],
    }
    if metadata:
        data["metadata"] = {"internal_boleto_id": str(boleto.id)}
    return {
        "id": event_id or f"hook_{uuid4().hex}",
        "type": event_type,
        "data": data,
    }


def _event(payload):
    return WebhookEvent.objects.create(
        provider_event_id=payload["id"],
        event_type=payload["type"],
        payload=payload,
        payload_sha256="0" * 64,
        authenticity_status="VERIFIED",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("event_type", "expected_status", "timestamp_field"),
    [
        ("order.paid", BoletoStatus.PAID, "paid_at"),
        ("order.payment_failed", BoletoStatus.FAILED, "failed_at"),
        ("order.canceled", BoletoStatus.CANCELED, "canceled_at"),
    ],
)
def test_order_event_updates_boleto_and_audit_link(
    boleto,
    event_type,
    expected_status,
    timestamp_field,
):
    event = _event(_payload(boleto, event_type))

    assert process_webhook_event(event)

    boleto.refresh_from_db()
    event.refresh_from_db()
    assert boleto.status == expected_status
    assert getattr(boleto, timestamp_field) is not None
    assert event.boleto == boleto
    assert event.processing_status == ProcessingStatus.PROCESSED
    assert event.attempts == 1


@pytest.mark.django_db
def test_charge_partial_cancel_and_refund_progress_without_regression(boleto):
    boleto.status = BoletoStatus.PAID
    boleto.save(update_fields=["status", "updated_at"])

    partial = _event(_payload(boleto, "charge.partial_canceled"))
    refunded = _event(_payload(boleto, "charge.refunded"))
    stale_pending = _event(_payload(boleto, "charge.pending"))

    assert process_webhook_event(partial)
    assert process_webhook_event(refunded)
    assert process_webhook_event(stale_pending)

    boleto.refresh_from_db()
    stale_pending.refresh_from_db()
    assert boleto.status == BoletoStatus.REFUNDED
    assert boleto.refunded_at is not None
    assert stale_pending.boleto == boleto
    assert stale_pending.processing_status == ProcessingStatus.IGNORED


@pytest.mark.django_db
def test_same_business_status_is_idempotent(boleto):
    boleto.status = BoletoStatus.PAID
    boleto.paid_at = timezone.now()
    boleto.save(update_fields=["status", "paid_at", "updated_at"])
    first_paid_at = boleto.paid_at
    event = _event(_payload(boleto, "charge.paid"))

    assert process_webhook_event(event)

    boleto.refresh_from_db()
    assert boleto.status == BoletoStatus.PAID
    assert boleto.paid_at == first_paid_at


@pytest.mark.django_db
def test_unknown_boleto_event_is_audited_and_ignored(boleto):
    event = _event(_payload(boleto, "charge.future_status"))

    assert process_webhook_event(event)

    event.refresh_from_db()
    boleto.refresh_from_db()
    assert event.boleto == boleto
    assert event.processing_status == ProcessingStatus.IGNORED
    assert boleto.status == BoletoStatus.PENDING


@pytest.mark.django_db
def test_creation_unknown_is_reconciled_from_webhook_metadata(boleto):
    boleto.status = BoletoStatus.CREATION_UNKNOWN
    boleto.provider_order_id = None
    boleto.provider_charge_id = None
    boleto.provider_transaction_id = None
    boleto.save()
    event = _event(_payload(boleto, "order.paid"))

    assert process_webhook_event(event)

    boleto.refresh_from_db()
    assert boleto.status == BoletoStatus.PAID
    assert boleto.provider_order_id == "or_boleto_1"
    assert boleto.provider_charge_id == "ch_boleto_1"
    assert boleto.provider_transaction_id == "tran_boleto_1"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("provider_status", "expected_status"),
    [
        ("paid", BoletoStatus.PAID),
        ("canceled", BoletoStatus.CANCELED),
        ("expired", BoletoStatus.EXPIRED),
        ("failed", BoletoStatus.FAILED),
    ],
)
def test_order_closed_uses_explicit_nested_status(boleto, provider_status, expected_status):
    payload = _payload(boleto, "order.closed", status="closed")
    payload["data"]["charges"][0]["status"] = provider_status
    event = _event(payload)

    assert process_webhook_event(event)

    boleto.refresh_from_db()
    event.refresh_from_db()
    assert boleto.status == expected_status
    assert event.processing_status == ProcessingStatus.PROCESSED


@pytest.mark.django_db
def test_order_closed_inconclusive_is_ignored_without_notification(boleto):
    event = _event(_payload(boleto, "order.closed", status="closed"))

    assert process_webhook_event(event)

    boleto.refresh_from_db()
    event.refresh_from_db()
    assert boleto.status == BoletoStatus.PENDING
    assert event.processing_status == ProcessingStatus.IGNORED
    assert not NotificationOutbox.objects.exists()
    assert not WhatsAppMessage.objects.exists()


@pytest.mark.django_db
def test_order_closed_does_not_regress_final_state(boleto):
    boleto.status = BoletoStatus.PAID
    boleto.save(update_fields=["status", "updated_at"])
    payload = _payload(boleto, "order.closed", status="closed")
    payload["data"]["charges"][0]["status"] = "expired"
    event = _event(payload)

    assert process_webhook_event(event)

    boleto.refresh_from_db()
    event.refresh_from_db()
    assert boleto.status == BoletoStatus.PAID
    assert event.processing_status == ProcessingStatus.IGNORED


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "payload_path", "conflicting_value"),
    [
        ("provider_charge_id", ("charges", 0, "id"), "ch_conflict"),
        ("provider_order_id", ("order", "id"), "or_conflict"),
        (
            "provider_transaction_id",
            ("charges", 0, "last_transaction", "id"),
            "tran_conflict",
        ),
    ],
)
def test_internal_id_rejects_conflicting_provider_ids(
    boleto,
    field,
    payload_path,
    conflicting_value,
):
    payload = _payload(boleto, "order.paid")
    target = payload["data"]
    for key in payload_path[:-1]:
        target = target[key]
    target[payload_path[-1]] = conflicting_value
    event = _event(payload)

    assert not process_webhook_event(event)

    boleto.refresh_from_db()
    event.refresh_from_db()
    assert boleto.status == BoletoStatus.PENDING
    assert getattr(boleto, field) != conflicting_value
    assert event.processing_status == ProcessingStatus.FAILED
    assert event.error_code == "BOLETO_PROVIDER_ID_MISMATCH"
    assert event.error_detail == ""
    assert not NotificationOutbox.objects.exists()
    assert not WhatsAppMessage.objects.exists()


@pytest.mark.django_db
def test_internal_id_rejects_charge_owned_by_another_boleto(boleto):
    other = Boleto.objects.create(
        seller=boleto.seller,
        company=boleto.company,
        created_by_seller=boleto.seller,
        amount_cents=10_000,
        due_date=boleto.due_date,
        description="Outra cobrança",
        status=BoletoStatus.PENDING,
        idempotency_key="other-provider-owner",
        provider_order_id="or_other",
        provider_charge_id="ch_other",
        company_snapshot={},
    )
    boleto.provider_charge_id = None
    boleto.save(update_fields=["provider_charge_id", "updated_at"])
    payload = _payload(boleto, "order.paid")
    payload["data"]["charges"][0]["id"] = other.provider_charge_id
    event = _event(payload)

    assert not process_webhook_event(event)

    boleto.refresh_from_db()
    event.refresh_from_db()
    assert boleto.provider_charge_id is None
    assert boleto.status == BoletoStatus.PENDING
    assert event.error_code == "BOLETO_PROVIDER_ID_MISMATCH"


def test_state_machine_uses_explicit_transition_sets():
    assert BoletoStatus.REFUNDED not in ALLOWED_TRANSITIONS[BoletoStatus.CREATING]
    assert BoletoStatus.PARTIALLY_CANCELED not in ALLOWED_TRANSITIONS[
        BoletoStatus.CREATION_UNKNOWN
    ]
    assert BoletoStatus.PAID in ALLOWED_TRANSITIONS[BoletoStatus.CREATION_UNKNOWN]
    assert BoletoStatus.PAID in ALLOWED_TRANSITIONS[BoletoStatus.EXPIRED]


@pytest.mark.django_db
def test_explicit_missing_boleto_remains_reprocessable():
    missing_id = uuid4()
    payload = {
        "id": "hook_missing_boleto",
        "type": "order.paid",
        "data": {
            "id": "or_missing",
            "metadata": {"internal_boleto_id": str(missing_id)},
        },
    }
    event = _event(payload)

    assert not process_webhook_event(event)

    event.refresh_from_db()
    assert event.boleto is None
    assert event.processing_status == ProcessingStatus.FAILED
    assert event.error_code == "BOLETO_NOT_FOUND"


@pytest.mark.django_db
def test_endpoint_authentication_and_duplicate_delivery(settings, client, boleto):
    settings.PAGARME_WEBHOOK_AUTH_MODE = "basic"
    settings.PAGARME_WEBHOOK_BASIC_AUTH_USER = "pagarme"
    settings.PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD = "secret"
    payload = _payload(boleto, "order.paid", event_id="hook_duplicate")
    url = reverse("webhooks:pagarme_webhook")

    unauthorized = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert unauthorized.status_code == 401
    assert WebhookEvent.objects.count() == 0

    credentials = base64.b64encode(b"pagarme:secret").decode()
    headers = {"HTTP_AUTHORIZATION": f"Basic {credentials}"}
    first = client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )
    duplicate = client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert WebhookEvent.objects.count() == 1


def test_normalizer_tolerates_malformed_nested_provider_data():
    normalized = normalize_event(
        {
            "id": "hook_malformed",
            "type": "charge.updated",
            "data": {
                "id": {"unexpected": "object"},
                "order": [],
                "charges": ["invalid"],
                "metadata": {"internal_boleto_id": {"not": "scalar"}},
                "status": ["invalid"],
            },
        }
    )

    assert normalized.order_id is None
    assert normalized.charge_id is None
    assert normalized.transaction_id is None
    assert normalized.internal_boleto_id is None
    assert normalized.status is None
