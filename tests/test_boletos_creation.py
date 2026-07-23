"""Boleto emission, Pagar.me payload and reviewed UI tests."""
from dataclasses import replace
from datetime import date, timedelta
from unittest.mock import Mock, patch

import httpx
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.boletos.models import Boleto, BoletoStatus, Company
from apps.boletos.services.boleto_creation import (
    BoletoCreationData,
    create_boleto,
)
from apps.integrations.pagarme.client import PagarmeClient, PagarmeError
from apps.sellers.models import Seller
from apps.webhooks.pagarme_payload import normalize_event

VALID_CNPJ = "11222333000181"


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="Vendedor Emissor",
        whatsapp_phone="+5511999999999",
        max_payment_amount_cents=1_000_000,
    )


@pytest.fixture
def other_seller(db):
    return Seller.objects.create(
        name="Outro Vendedor",
        whatsapp_phone="+5511888888888",
        max_payment_amount_cents=1_000_000,
    )


@pytest.fixture
def manager(db):
    return get_user_model().objects.create_superuser(
        username="boleto-manager",
        email="manager@example.com",
        password="test-password",
    )


@pytest.fixture
def creation_data():
    return BoletoCreationData(
        cnpj="11.222.333/0001-81",
        legal_name="EMPRESA CLIENTE LTDA",
        trade_name="EMPRESA CLIENTE",
        email="financeiro@example.com",
        phone="11999999999",
        whatsapp_phone="11988888888",
        zip_code="01310-100",
        street="Avenida Paulista",
        number="1000",
        complement="10º andar",
        district="Bela Vista",
        city="São Paulo",
        state="SP",
        amount_cents=25_090,
        due_date=date.today() + timedelta(days=5),
        description="Serviços contratados",
        internal_reference="PED-100",
        internal_notes="Uso interno",
    )


@pytest.fixture
def provider_response():
    return {
        "id": "or_boleto_123",
        "status": "pending",
        "charges": [
            {
                "id": "ch_boleto_123",
                "status": "pending",
                "last_transaction": {
                    "id": "tran_boleto_123",
                    "line": "00190000090000000000000000000000000000000000",
                    "barcode": "00190000000000000000000000000000000000000000",
                    "pdf": "https://provider.example/boleto.pdf",
                },
            }
        ],
    }


def test_pagarme_client_uses_existing_auth_and_idempotency_header(settings, provider_response):
    settings.PAGARME_CREDENTIAL = "sk_test_existing"
    settings.PAGARME_SECRET_KEY = ""
    response = httpx.Response(
        200,
        json=provider_response,
        request=httpx.Request("POST", "https://api.pagar.me/core/v5/orders"),
    )

    with patch("apps.integrations.pagarme.client.httpx.post", return_value=response) as post:
        client = PagarmeClient()
        result = client.create_boleto_order(
            code="BOL-123",
            amount_cents=25_090,
            description="Serviços",
            due_date="2026-08-10",
            customer={
                "name": "EMPRESA",
                "email": "financeiro@example.com",
                "type": "company",
                "document": VALID_CNPJ,
                "document_type": "CNPJ",
                "address": {},
            },
            metadata={
                "aggregate_type": "boleto",
                "internal_boleto_id": "internal-123",
                "seller_id": "seller-123",
                "reference": "PED-100",
            },
            idempotency_key="logical-attempt-123",
        )

    assert result == provider_response
    _, kwargs = post.call_args
    assert kwargs["headers"]["Authorization"].startswith("Basic ")
    assert kwargs["headers"]["Idempotency-Key"] == "logical-attempt-123"
    assert kwargs["json"]["payments"][0]["payment_method"] == "boleto"
    boleto_payload = kwargs["json"]["payments"][0]["boleto"]
    assert boleto_payload["due_at"] == "2026-08-10T23:59:59Z"
    assert boleto_payload["instructions"] == (
        "Após o vencimento: multa de 2% e juros de mora de 1% ao mês."
    )
    assert boleto_payload["interest"] == {
        "days": 1,
        "type": "percentage",
        "amount": 1,
    }
    assert boleto_payload["fine"] == {
        "days": 1,
        "type": "percentage",
        "amount": 2,
    }
    assert kwargs["json"]["customer"]["type"] == "company"
    assert kwargs["json"]["customer"]["document_type"] == "CNPJ"
    assert kwargs["json"]["metadata"]["internal_boleto_id"] == "internal-123"


def test_existing_webhook_normalizer_extracts_boleto_correlation(provider_response):
    payload = {
        "id": "hook_boleto_123",
        "type": "order.paid",
        "data": {
            **provider_response,
            "metadata": {
                "aggregate_type": "boleto",
                "internal_boleto_id": "d34db33f-0000-4000-8000-000000000001",
            },
        },
    }

    normalized = normalize_event(payload)

    assert normalized.internal_boleto_id == "d34db33f-0000-4000-8000-000000000001"
    assert normalized.order_id == "or_boleto_123"
    assert normalized.charge_id == "ch_boleto_123"
    assert normalized.transaction_id == "tran_boleto_123"


@pytest.mark.django_db
def test_create_boleto_persists_provider_ids_snapshot_and_metadata(
    seller,
    creation_data,
    provider_response,
):
    client = Mock()
    client.create_boleto_order.return_value = provider_response

    result = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="create-success",
        client=client,
    )

    assert result.success
    boleto = result.boleto
    assert boleto.status == BoletoStatus.PENDING
    assert boleto.provider_order_id == "or_boleto_123"
    assert boleto.provider_charge_id == "ch_boleto_123"
    assert boleto.provider_transaction_id == "tran_boleto_123"
    assert boleto.digitable_line
    assert boleto.pdf_url == "https://provider.example/boleto.pdf"
    assert boleto.company.cnpj == VALID_CNPJ
    assert boleto.company_snapshot["legal_name"] == "EMPRESA CLIENTE LTDA"
    call = client.create_boleto_order.call_args.kwargs
    assert call["metadata"]["internal_boleto_id"] == str(boleto.id)
    assert call["metadata"]["seller_id"] == str(seller.id)
    assert call["idempotency_key"] == "create-success"


@pytest.mark.django_db
def test_double_confirmation_reuses_boleto_without_second_provider_call(
    seller,
    creation_data,
    provider_response,
):
    client = Mock()
    client.create_boleto_order.return_value = provider_response

    first = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="double-click",
        client=client,
    )
    second = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="double-click",
        client=client,
    )

    assert second.boleto == first.boleto
    assert second.idempotent_replay
    assert Boleto.objects.count() == 1
    client.create_boleto_order.assert_called_once()


@pytest.mark.django_db
def test_same_key_with_different_payload_is_rejected(
    seller,
    creation_data,
    provider_response,
):
    client = Mock()
    client.create_boleto_order.return_value = provider_response
    create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="payload-conflict",
        client=client,
    )

    result = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=replace(creation_data, amount_cents=30_000),
        idempotency_key="payload-conflict",
        client=client,
    )

    assert not result.success
    assert result.boleto is None
    assert "dados diferentes" in result.error_message
    client.create_boleto_order.assert_called_once()


@pytest.mark.django_db
def test_timeout_marks_creation_unknown_and_blocks_automatic_retry(seller, creation_data):
    client = Mock()
    client.create_boleto_order.side_effect = httpx.ReadTimeout("timeout")

    first = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="timeout-key",
        client=client,
    )
    second = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="timeout-key",
        client=client,
    )

    assert first.uncertain
    assert first.boleto.status == BoletoStatus.CREATION_UNKNOWN
    assert second.idempotent_replay
    assert second.uncertain
    client.create_boleto_order.assert_called_once()


@pytest.mark.django_db
def test_provider_validation_error_marks_creation_error(seller, creation_data):
    client = Mock()
    client.create_boleto_order.side_effect = PagarmeError(422, {"message": "invalid"})

    result = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="provider-error",
        client=client,
    )

    assert not result.success
    assert result.boleto.status == BoletoStatus.CREATION_ERROR
    assert result.boleto.creation_response == {
        "provider_error": True,
        "status_code": 422,
    }


@pytest.mark.django_db
def test_incomplete_provider_response_is_unknown(seller, creation_data):
    client = Mock()
    client.create_boleto_order.return_value = {"id": "or_without_charge"}

    result = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="incomplete-response",
        client=client,
    )

    assert result.uncertain
    assert result.boleto.status == BoletoStatus.CREATION_UNKNOWN
    assert result.boleto.provider_order_id is None


@pytest.mark.django_db
def test_provider_urls_and_numeric_boleto_fields_are_sanitized(
    seller,
    creation_data,
    provider_response,
):
    response = {
        **provider_response,
        "charges": [
            {
                **provider_response["charges"][0],
                "last_transaction": {
                    **provider_response["charges"][0]["last_transaction"],
                    "line": "00190.00009 00000.000000",
                    "barcode": "00190 12345",
                    "pdf": "javascript:alert(document.domain)",
                },
            }
        ],
    }
    client = Mock()
    client.create_boleto_order.return_value = response

    result = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="sanitize-provider-response",
        client=client,
    )

    assert result.success
    assert result.boleto.digitable_line == "001900000900000000000"
    assert result.boleto.barcode == "0019012345"
    assert result.boleto.pdf_url == ""


@pytest.mark.django_db
def test_oversized_provider_identifier_keeps_creation_uncertain(
    seller,
    creation_data,
    provider_response,
):
    client = Mock()
    client.create_boleto_order.return_value = {
        **provider_response,
        "id": "x" * 101,
    }

    result = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="oversized-provider-id",
        client=client,
    )

    assert result.uncertain
    assert result.boleto.status == BoletoStatus.CREATION_UNKNOWN
    assert result.boleto.provider_order_id is None


@pytest.mark.django_db
def test_existing_company_is_reused_and_updated(seller, creation_data, provider_response):
    Company.objects.create(
        cnpj=VALID_CNPJ,
        legal_name="NOME ANTIGO",
        zip_code="00000000",
        street="Rua Antiga",
        number="1",
        district="Centro",
        city="São Paulo",
        state="SP",
    )
    client = Mock()
    client.create_boleto_order.return_value = provider_response

    result = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=creation_data,
        idempotency_key="company-reuse",
        client=client,
    )

    assert Company.objects.count() == 1
    assert result.boleto.company.legal_name == creation_data.legal_name
    historical_snapshot = result.boleto.company_snapshot.copy()
    result.boleto.company.legal_name = "NOME ALTERADO DEPOIS"
    result.boleto.company.save(update_fields=["legal_name", "updated_at"])
    result.boleto.refresh_from_db()
    assert result.boleto.company_snapshot == historical_snapshot


def review_post_data(seller):
    return {
        "action": "review",
        "seller_id": str(seller.id),
        "cnpj": "11.222.333/0001-81",
        "legal_name": "EMPRESA CLIENTE LTDA",
        "trade_name": "EMPRESA",
        "email": "financeiro@example.com",
        "phone": "(11) 99999-9999",
        "whatsapp_phone": "(11) 98888-8888",
        "zip_code": "01310-100",
        "street": "Avenida Paulista",
        "number": "1000",
        "complement": "",
        "district": "Bela Vista",
        "city": "São Paulo",
        "state": "SP",
        "amount_display": "250,90",
        "due_date": (date.today() + timedelta(days=5)).isoformat(),
        "description": "Serviços contratados",
        "internal_reference": "PED-100",
        "internal_notes": "",
    }


@pytest.mark.django_db
def test_manager_review_does_not_call_pagarme(client, manager, seller):
    client.force_login(manager)

    with patch("apps.boletos.views.create_boleto") as create:
        response = client.post(reverse("boletos:manager_create"), data=review_post_data(seller))

    assert response.status_code == 200
    assert response.context["review"]["amount_cents"] == 25_090
    assert response.context["review_token"]
    create.assert_not_called()


@pytest.mark.django_db
def test_back_from_review_preserves_form_data(client, manager, seller):
    client.force_login(manager)
    review = client.post(reverse("boletos:manager_create"), data=review_post_data(seller))

    response = client.post(
        reverse("boletos:manager_create"),
        data={
            "action": "edit",
            "review_token": review.context["review_token"],
        },
    )

    assert response.status_code == 200
    assert response.context["form"].initial["legal_name"] == "EMPRESA CLIENTE LTDA"
    assert response.context["form"].initial["amount_display"] == "250,90"


@pytest.mark.django_db
def test_manager_confirmation_creates_and_redirects(
    client,
    manager,
    seller,
    provider_response,
):
    client.force_login(manager)
    review = client.post(reverse("boletos:manager_create"), data=review_post_data(seller))
    token = review.context["review_token"]

    with patch("apps.boletos.services.boleto_creation.PagarmeClient") as client_class:
        client_class.return_value.create_boleto_order.return_value = provider_response
        response = client.post(
            reverse("boletos:manager_create"),
            data={"action": "confirm", "review_token": token},
        )

    boleto = Boleto.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("boletos:manager_detail", kwargs={"boleto_id": boleto.id})
    assert boleto.created_by_user == manager
    assert boleto.seller == seller


@pytest.mark.django_db
def test_tampered_review_token_is_rejected(client, manager):
    client.force_login(manager)

    response = client.post(
        reverse("boletos:manager_create"),
        data={"action": "confirm", "review_token": "tampered"},
    )

    assert response.status_code == 400
    assert not Boleto.objects.exists()


@pytest.mark.django_db
def test_seller_creation_page_is_bound_to_authenticated_seller(client, seller):
    with patch("apps.sellers.middleware.get_seller_from_session", return_value=seller):
        response = client.get(reverse("boletos:seller_create"))

    assert response.status_code == 200
    assert response.context["seller"] == seller
    assert response.context["sellers"] is None
    assert b'class="boleto-cnpj-lookup"' in response.content
    assert b"if(input)input.value=data[key]||''" in response.content
    assert b"if(input&&!input.value)" not in response.content


@pytest.mark.django_db
def test_seller_cannot_review_for_another_seller(client, seller, other_seller):
    payload = review_post_data(other_seller)

    with patch("apps.sellers.middleware.get_seller_from_session", return_value=seller):
        response = client.post(reverse("boletos:seller_create"), data=payload)

    assert response.status_code == 403
    assert not Boleto.objects.exists()


@pytest.mark.django_db
def test_seller_cannot_view_another_sellers_boleto(
    client,
    seller,
    other_seller,
    creation_data,
    provider_response,
):
    provider = Mock()
    provider.create_boleto_order.return_value = provider_response
    result = create_boleto(
        seller=other_seller,
        actor_seller=other_seller,
        data=creation_data,
        idempotency_key="other-detail",
        client=provider,
    )

    with patch("apps.sellers.middleware.get_seller_from_session", return_value=seller):
        response = client.get(
            reverse("boletos:seller_detail", kwargs={"boleto_id": result.boleto.id})
        )

    assert response.status_code == 404
