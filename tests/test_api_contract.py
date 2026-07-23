"""Regression tests for the public API contract."""

from unittest.mock import patch
from uuid import UUID

import pytest
from django.urls import reverse

from apps.notifications.models import NotificationOutbox
from apps.payment_links.models import PaymentLink, PaymentLinkStatus
from apps.sellers.models import Seller
from apps.sellers.services import generate_invitation


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="API Contract",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1_000_000,
        is_active=True,
    )


def _authenticate(client, seller):
    _, token = generate_invitation(seller=seller)
    client.get(reverse("sellers:activate", kwargs={"token": token}))
    client.post(reverse("sellers:confirm_activation", kwargs={"token": token}))


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    (("installments", 4), ("expires_in_minutes", 9), ("expires_in_minutes", "invalid")),
)
def test_create_rejects_invalid_fields_before_provider_call(client, seller, field, value):
    _authenticate(client, seller)
    payload = {"reference": "API-1", "amount_cents": 1000, "installments": 1, field: value}

    with patch("apps.payment_links.use_cases.PagarmeClient") as provider:
        response = client.post(
            "/api/v1/payment-links/",
            payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=f"invalid-{field}-{value}",
        )

    assert response.status_code == 400
    assert field in response.json()["error"]["field_errors"]
    provider.assert_not_called()


@pytest.mark.django_db
def test_create_idempotency_compares_optional_fields(client, seller):
    _authenticate(client, seller)
    provider_response = {"id": "pl_contract", "url": "https://pay.example/link", "status": "active"}

    with patch("apps.payment_links.use_cases.PagarmeClient") as provider:
        provider.return_value.create_payment_link.return_value = provider_response
        first = client.post(
            "/api/v1/payment-links/",
            {
                "reference": "API-2",
                "amount_cents": 1000,
                "installments": 1,
                "description": "original",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="same-key",
        )
        second = client.post(
            "/api/v1/payment-links/",
            {
                "reference": "API-2",
                "amount_cents": 1000,
                "installments": 1,
                "description": "changed",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="same-key",
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert provider.return_value.create_payment_link.call_count == 1


@pytest.mark.django_db
def test_create_normalizes_masked_brazilian_phone(client, seller):
    _authenticate(client, seller)
    provider_response = {"id": "pl_phone", "url": "https://pay.example/phone", "status": "active"}

    with patch("apps.payment_links.use_cases.PagarmeClient") as provider:
        provider.return_value.create_payment_link.return_value = provider_response
        response = client.post(
            "/api/v1/payment-links/",
            {
                "reference": "API-PHONE",
                "amount_cents": 1000,
                "installments": 1,
                "customer_phone": "(31) 99999-9999",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phone-key",
        )

    assert response.status_code == 201
    assert PaymentLink.objects.get(reference="API-PHONE").customer_phone == "+5531999999999"


@pytest.mark.django_db
def test_resend_uses_idempotency_key(client, seller):
    _authenticate(client, seller)
    link = PaymentLink.objects.create(
        seller=seller,
        reference="API-3",
        amount_cents=1000,
        installments=1,
        status=PaymentLinkStatus.ACTIVE,
        payment_url="https://pay.example/link",
        idempotency_key="create-api-3",
    )
    url = f"/api/v1/payment-links/{link.id}/resend/"

    first = client.post(url, HTTP_IDEMPOTENCY_KEY="resend-1")
    repeated = client.post(url, HTTP_IDEMPOTENCY_KEY="resend-1")
    different = client.post(url, HTTP_IDEMPOTENCY_KEY="resend-2")

    assert first.status_code == repeated.status_code == different.status_code == 202
    assert first.json()["data"]["whatsapp"]["seller"]["status"] == "queued"
    assert repeated.json()["data"]["whatsapp"]["seller"]["status"] == "duplicate"
    assert different.json()["data"]["whatsapp"]["seller"]["status"] == "queued"
    assert NotificationOutbox.objects.filter(aggregate_id=link.id).count() == 2


def test_every_response_exposes_request_id(client):
    response = client.get("/health/")

    assert UUID(response["X-Request-ID"])


def test_openapi_contract_is_valid_json():
    import json
    from pathlib import Path

    contract = json.loads(Path("docs/openapi.json").read_text(encoding="utf-8"))
    assert contract["openapi"] == "3.1.0"
    expected = {
        "/api/v1/payment-links/": {"get", "post"},
        "/api/v1/payment-links/{link_id}/": {"get"},
        "/api/v1/payment-links/{link_id}/resend/": {"post"},
        "/api/v1/boletos/cnpj/{cnpj}/": {"get"},
        "/api/v1/freight/cep/": {"post"},
        "/api/v1/freight/calculate/": {"post"},
        "/api/v1/webhooks/pagarme/": {"post"},
        "/health/": {"get"},
        "/health/ready/": {"get"},
    }
    for path, methods in expected.items():
        assert methods <= set(contract["paths"][path])
