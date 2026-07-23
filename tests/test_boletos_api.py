"""Contract, authorization and lifecycle tests for the boleto API."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.boletos.models import Boleto, BoletoStatus, Company
from apps.integrations.auth import hash_api_key
from apps.integrations.n8n.models import ApiClient
from apps.notifications.models import NotificationOutbox
from apps.sellers.models import Seller
from apps.sellers.services import generate_invitation


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="Seller Boleto API",
        whatsapp_phone="+5511999999999",
        max_payment_amount_cents=1_000_000,
        is_active=True,
    )


@pytest.fixture
def company(db):
    return Company.objects.create(
        cnpj="11222333000181",
        legal_name="CLIENTE API LTDA",
        trade_name="Cliente API",
        email="financeiro@example.com",
        phone="11988888888",
        whatsapp_phone="11988888888",
        zip_code="01310100",
        street="Avenida Paulista",
        number="1000",
        complement="Sala 1",
        district="Bela Vista",
        city="São Paulo",
        state="SP",
    )


@pytest.fixture
def boleto(seller, company):
    return Boleto.objects.create(
        seller=seller,
        company=company,
        created_by_seller=seller,
        amount_cents=25_090,
        due_date=date.today() + timedelta(days=10),
        description="Serviços",
        internal_reference="API-BOL-1",
        status=BoletoStatus.PENDING,
        idempotency_key="create-existing",
        provider_order_id="or_api",
        provider_charge_id="ch_api",
        provider_status="pending",
        digitable_line="00190000090000000000000000000000000000000000",
        pdf_url="https://provider.example/boleto.pdf",
        company_snapshot={
            "cnpj": company.cnpj,
            "legal_name": company.legal_name,
            "trade_name": company.trade_name,
            "email": company.email,
            "phone": company.phone,
            "whatsapp_phone": company.whatsapp_phone,
            "address": {
                "zip_code": company.zip_code,
                "street": company.street,
                "number": company.number,
                "complement": company.complement,
                "district": company.district,
                "city": company.city,
                "state": company.state,
                "country": "BR",
            },
        },
    )


def _authenticate(client, seller):
    _, token = generate_invitation(seller=seller)
    client.get(reverse("sellers:activate", kwargs={"token": token}))
    client.post(reverse("sellers:confirm_activation", kwargs={"token": token}))


def _create_payload(seller):
    return {
        "seller_id": str(seller.id),
        "cnpj": "11.222.333/0001-81",
        "legal_name": "CLIENTE API LTDA",
        "trade_name": "Cliente API",
        "email": "financeiro@example.com",
        "phone": "(11) 98888-8888",
        "whatsapp_phone": "(11) 98888-8888",
        "zip_code": "01310-100",
        "street": "Avenida Paulista",
        "number": "1000",
        "complement": "Sala 1",
        "district": "Bela Vista",
        "city": "São Paulo",
        "state": "sp",
        "amount_cents": 25_090,
        "due_date": (date.today() + timedelta(days=10)).isoformat(),
        "description": "Serviços",
        "internal_reference": "API-NEW",
    }


@pytest.mark.django_db
def test_create_list_detail_and_status_with_seller_session(client, seller):
    _authenticate(client, seller)
    provider_response = {
        "id": "or_created",
        "status": "pending",
        "charges": [
            {
                "id": "ch_created",
                "status": "pending",
                "last_transaction": {
                    "id": "tran_created",
                    "line": "00190000090000000000000000000000000000000000",
                    "pdf": "https://provider.example/created.pdf",
                },
            }
        ],
    }
    with patch("apps.boletos.services.boleto_creation.PagarmeClient") as provider:
        provider.return_value.create_boleto_order.return_value = provider_response
        created = client.post(
            "/api/v1/boletos/",
            _create_payload(seller),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="api-create-1",
        )

    assert created.status_code == 201
    boleto_id = created.json()["data"]["id"]
    listed = client.get("/api/v1/boletos/?status=PENDING&limit=10")
    detailed = client.get(f"/api/v1/boletos/{boleto_id}/")
    situation = client.get(f"/api/v1/boletos/{boleto_id}/status/")

    assert listed.status_code == detailed.status_code == situation.status_code == 200
    assert listed.json()["data"][0]["id"] == boleto_id
    assert detailed.json()["data"]["digitable_line"]
    assert situation.json()["data"]["status"] == BoletoStatus.PENDING


@pytest.mark.django_db
def test_api_key_requires_scope_and_never_crosses_seller(client, seller, boleto, settings):
    settings.API_KEY_PEPPER = "boleto-api-pepper"
    raw_key = "vly_live_boleto_api_key"
    ApiClient.objects.create(
        name="Boleto read",
        key_prefix=raw_key[:12],
        key_hash=hash_api_key(raw_key),
        scopes=["boletos:read"],
    )
    other = Seller.objects.create(
        name="Other",
        whatsapp_phone="+5511977777777",
        max_payment_amount_cents=1_000_000,
    )

    own = client.get(
        f"/api/v1/boletos/{boleto.id}/?seller_id={seller.id}",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    crossed = client.get(
        f"/api/v1/boletos/{boleto.id}/?seller_id={other.id}",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
    )
    write = client.post(
        f"/api/v1/boletos/{boleto.id}/cancel/?seller_id={seller.id}",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        HTTP_IDEMPOTENCY_KEY="cancel-no-scope",
    )

    assert own.status_code == 200
    assert crossed.status_code == 404
    assert write.status_code == 403


@pytest.mark.django_db
def test_cancel_is_idempotent_and_never_refunds_paid_boleto(client, seller, boleto):
    _authenticate(client, seller)
    with patch("apps.boletos.services.boleto_cancellation.PagarmeClient") as provider:
        provider.return_value.cancel_boleto_charge.return_value = {
            "id": boleto.provider_charge_id,
            "status": "canceled",
        }
        first = client.post(
            f"/api/v1/boletos/{boleto.id}/cancel/",
            HTTP_IDEMPOTENCY_KEY="cancel-1",
        )
        repeated = client.post(
            f"/api/v1/boletos/{boleto.id}/cancel/",
            HTTP_IDEMPOTENCY_KEY="cancel-1",
        )

    assert first.status_code == repeated.status_code == 200
    assert provider.return_value.cancel_boleto_charge.call_count == 1
    boleto.refresh_from_db()
    assert boleto.status == BoletoStatus.CANCELED

    boleto.status = BoletoStatus.PAID
    boleto.save(update_fields=["status", "updated_at"])
    rejected = client.post(
        f"/api/v1/boletos/{boleto.id}/cancel/",
        HTTP_IDEMPOTENCY_KEY="never-refund",
    )
    assert rejected.status_code == 422


@pytest.mark.django_db
def test_resend_uses_idempotency_key(client, seller, boleto):
    _authenticate(client, seller)
    url = f"/api/v1/boletos/{boleto.id}/resend/"

    first = client.post(url, HTTP_IDEMPOTENCY_KEY="resend-1")
    repeated = client.post(url, HTTP_IDEMPOTENCY_KEY="resend-1")

    assert first.status_code == repeated.status_code == 202
    assert first.json()["data"]["deliveries"][0]["status"] == "queued"
    assert repeated.json()["data"]["deliveries"][0]["status"] == "duplicate"
    assert NotificationOutbox.objects.count() == 2


@pytest.mark.django_db
def test_second_copy_preserves_original_and_relation(client, seller, boleto):
    _authenticate(client, seller)
    boleto.status = BoletoStatus.CANCELED
    boleto.save(update_fields=["status", "updated_at"])
    provider_response = {
        "id": "or_second",
        "status": "pending",
        "charges": [
            {
                "id": "ch_second",
                "status": "pending",
                "last_transaction": {
                    "id": "tran_second",
                    "line": "23790000000000000000000000000000000000000000",
                    "pdf": "https://provider.example/second.pdf",
                },
            }
        ],
    }
    with patch("apps.boletos.services.boleto_creation.PagarmeClient") as provider:
        provider.return_value.create_boleto_order.return_value = provider_response
        response = client.post(
            f"/api/v1/boletos/{boleto.id}/second-copy/",
            {"due_date": (date.today() + timedelta(days=20)).isoformat()},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="second-copy-1",
        )

    assert response.status_code == 201
    replacement = Boleto.objects.get(id=response.json()["data"]["id"])
    boleto.refresh_from_db()
    assert replacement.reissued_from == boleto
    assert replacement.amount_cents == boleto.amount_cents
    assert replacement.digitable_line != boleto.digitable_line
    assert boleto.status == BoletoStatus.CANCELED
