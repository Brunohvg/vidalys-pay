"""Boleto notifications through the existing reliable WhatsApp outbox."""

from datetime import date

import pytest

from apps.boletos.models import Boleto, BoletoStatus, Company
from apps.notifications.models import (
    NotificationOutbox,
    OutboxStatus,
    RecipientType,
    WhatsAppMessage,
)
from apps.notifications.whatsapp_service import (
    queue_boleto_created,
    queue_boleto_status,
)
from apps.sellers.models import Selle
from apps.webhooks.models import WebhookEvent
from apps.webhooks.processor import process_webhook_event


@pytest.fixture
def boleto(db):
    seller = Seller.objects.create(
        name="Vendedora de Boletos",
        whatsapp_phone="+5511999999999",
        max_payment_amount_cents=1_000_000,
    )
    company = Company.objects.create(
        cnpj="11222333000181",
        legal_name="CLIENTE BOLETO LTDA",
        whatsapp_phone="11988888888",
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
        amount_cents=25_090,
        due_date=date(2026, 8, 10),
        description="Serviços",
        internal_reference="PED-100",
        status=BoletoStatus.PENDING,
        idempotency_key="notification-test",
        provider_order_id="or_notify",
        provider_charge_id="ch_notify",
        digitable_line="00190000090000000000000000000000000000000000",
        pdf_url="https://provider.example/boleto.pdf",
        company_snapshot={
            "cnpj": company.cnpj,
            "legal_name": company.legal_name,
            "phone": "",
            "whatsapp_phone": company.whatsapp_phone,
        },
    )


@pytest.mark.django_db
def test_creation_queues_seller_and_customer_with_boleto_history(boleto):
    results = queue_boleto_created(boleto=boleto)

    assert [result.status for result in results] == ["queued", "queued"]
    assert NotificationOutbox.objects.filter(aggregate_type="boleto").count() == 2
    assert set(
        WhatsAppMessage.objects.values_list("recipient_type", flat=True)
    ) == {RecipientType.SELLER, RecipientType.CUSTOMER}
    assert not WhatsAppMessage.objects.filter(boleto__isnull=True).exists()

    customer = WhatsAppMessage.objects.get(recipient_type=RecipientType.CUSTOMER)
    assert customer.recipient_phone == "5511988888888"
    assert boleto.digitable_line in customer.rendered_text
    assert boleto.pdf_url in customer.rendered_text


@pytest.mark.django_db
def test_boleto_notification_is_never_duplicated_even_after_delivery(boleto):
    first = queue_boleto_created(boleto=boleto)
    NotificationOutbox.objects.update(status=OutboxStatus.DONE)

    second = queue_boleto_created(boleto=boleto)

    assert [result.status for result in first] == ["queued", "queued"]
    assert [result.status for result in second] == ["duplicate", "duplicate"]
    assert NotificationOutbox.objects.count() == 2
    assert WhatsAppMessage.objects.count() == 2


@pytest.mark.django_db
def test_paid_notifies_configured_seller_customer_and_managers(settings, boleto):
    settings.BOLETO_NOTIFY_CUSTOMER_ON_PAID = True
    settings.BOLETO_MANAGER_WHATSAPP_PHONES = [
        "+5511977777777",
        "+5511966666666",
    ]
    boleto.status = BoletoStatus.PAID
    boleto.paid_at = None

    results = queue_boleto_status(boleto=boleto, event_type="boleto_paid")

    assert len(results) == 4
    assert WhatsAppMessage.objects.filter(recipient_type=RecipientType.SELLER).count() == 1
    assert WhatsAppMessage.objects.filter(recipient_type=RecipientType.CUSTOMER).count() == 1
    assert WhatsAppMessage.objects.filter(recipient_type=RecipientType.MANAGER).count() == 2


@pytest.mark.django_db
def test_failure_only_notifies_seller_without_technical_detail(settings, boleto):
    settings.BOLETO_MANAGER_WHATSAPP_PHONES = ["+5511977777777"]
    settings.BOLETO_NOTIFY_CUSTOMER_ON_PAID = True

    queue_boleto_status(boleto=boleto, event_type="boleto_failed")

    message = WhatsAppMessage.objects.get()
    assert message.recipient_type == RecipientType.SELLER
    assert "Falha na cobrança" in message.rendered_text
    assert "gateway" not in message.rendered_text.lower()


@pytest.mark.django_db
def test_webhook_queues_notification_only_after_commit(
    boleto,
    django_capture_on_commit_callbacks,
):
    payload = {
        "id": "hook_notify_paid",
        "type": "order.paid",
        "data": {
            "id": boleto.provider_order_id,
            "status": "paid",
            "metadata": {"internal_boleto_id": str(boleto.id)},
            "charges": [{"id": boleto.provider_charge_id}],
        },
    }
    event = WebhookEvent.objects.create(
        provider_event_id=payload["id"],
        event_type=payload["type"],
        payload=payload,
        payload_sha256="0" * 64,
        authenticity_status="VERIFIED",
    )

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        assert process_webhook_event(event)
        assert NotificationOutbox.objects.count() == 0

    assert len(callbacks) == 1
    callbacks[0]()
    assert NotificationOutbox.objects.count() == 1
    assert WhatsAppMessage.objects.get().event_type == "boleto_paid"

    process_webhook_event(event)
    assert NotificationOutbox.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("seller_phone", "expected_status"),
    [
        ("", "missing_phone"),
        ("123", "invalid_phone"),
    ],
)
def test_invalid_or_missing_seller_phone_never_creates_outbox(
    boleto,
    seller_phone,
    expected_status,
):
    boleto.seller.whatsapp_phone = seller_phone
    boleto.seller.save(update_fields=["whatsapp_phone", "updated_at"])
    boleto.company_snapshot["whatsapp_phone"] = ""
    boleto.company_snapshot["phone"] = ""
    boleto.save(update_fields=["company_snapshot", "updated_at"])

    results = queue_boleto_created(boleto=boleto)

    assert results[0].status == expected_status
    assert results[1].status == "missing_phone"
    assert not NotificationOutbox.objects.exists()
    assert not WhatsAppMessage.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("phone", ["11999999999", "5511999999999"])
def test_valid_phone_is_normalized_once_to_country_code(boleto, phone):
    boleto.seller.whatsapp_phone = phone
    boleto.seller.save(update_fields=["whatsapp_phone", "updated_at"])
    boleto.company_snapshot["whatsapp_phone"] = ""
    boleto.company_snapshot["phone"] = ""
    boleto.save(update_fields=["company_snapshot", "updated_at"])

    results = queue_boleto_created(boleto=boleto)

    assert results[0].status == "queued"
    assert results[0].recipient_phone == "5511999999999"
    assert WhatsAppMessage.objects.get().recipient_phone == "5511999999999"


@pytest.mark.django_db
def test_invalid_manager_phone_never_creates_outbox(settings, boleto):
    settings.BOLETO_MANAGER_WHATSAPP_PHONES = ["invalid", "55123"]
    settings.BOLETO_NOTIFY_CUSTOMER_ON_PAID = False
    boleto.seller.whatsapp_phone = ""
    boleto.seller.save(update_fields=["whatsapp_phone", "updated_at"])

    results = queue_boleto_status(boleto=boleto, event_type="boleto_paid")

    assert [result.status for result in results] == [
        "missing_phone",
        "invalid_phone",
        "invalid_phone",
    ]
    assert not NotificationOutbox.objects.exists()
    assert not WhatsAppMessage.objects.exists()
