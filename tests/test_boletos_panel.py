"""Role-scoped boleto panel, filtering, metrics and detail tests."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.boletos.models import Boleto, BoletoStatus, Company
from apps.notifications.models import WhatsAppMessage
from apps.sellers.models import Seller
from apps.webhooks.models import WebhookEvent


@pytest.fixture
def manager(db):
    return get_user_model().objects.create_superuser(
        username="panel-manager",
        email="manager@example.com",
        password="password",
    )


@pytest.fixture
def sellers(db):
    return [
        Seller.objects.create(
            name=f"Vendedor {index}",
            whatsapp_phone=f"+55119999999{index:02d}",
            max_payment_amount_cents=1_000_000,
        )
        for index in range(2)
    ]


@pytest.fixture
def companies(db):
    return [
        Company.objects.create(
            cnpj=cnpj,
            legal_name=name,
            trade_name=trade_name,
            zip_code="01310100",
            street="Avenida Paulista",
            number="1000",
            district="Bela Vista",
            city="São Paulo",
            state="SP",
        )
        for cnpj, name, trade_name in [
            ("11222333000181", "ALFA SERVIÇOS LTDA", "ALFA"),
            ("11444777000161", "BETA COMÉRCIO LTDA", "BETA"),
        ]
    ]


def make_boleto(*, seller, company, index, status=BoletoStatus.PENDING):
    return Boleto.objects.create(
        seller=seller,
        company=company,
        created_by_seller=seller,
        amount_cents=10_000 + index,
        due_date=date.today() + timedelta(days=index % 10),
        description="Serviços",
        internal_reference=f"REF-{index:03d}",
        status=status,
        idempotency_key=f"panel-{seller.id}-{index}",
        company_snapshot={
            "cnpj": company.cnpj,
            "legal_name": company.legal_name,
            "phone": "",
            "whatsapp_phone": "",
        },
    )


@pytest.mark.django_db
def test_manager_list_filters_searches_orders_and_paginates(
    client,
    manager,
    sellers,
    companies,
    django_assert_max_num_queries,
):
    client.force_login(manager)
    for index in range(23):
        make_boleto(
            seller=sellers[index % 2],
            company=companies[index % 2],
            index=index,
            status=BoletoStatus.PAID if index % 3 == 0 else BoletoStatus.PENDING,
        )

    with django_assert_max_num_queries(8):
        first_page = client.get(reverse("boletos:manager_list"))
    filtered = client.get(
        reverse("boletos:manager_list"),
        {
            "q": "ALFA",
            "seller": sellers[0].id,
            "status": BoletoStatus.PAID,
            "ordering": "amount_desc",
        },
    )
    no_match = client.get(reverse("boletos:manager_list"), {"q": "INEXISTENTE"})
    malformed = client.get(
        reverse("boletos:manager_list"),
        {"seller": "invalid", "created_from": "2026-99-99"},
    )

    assert first_page.status_code == 200
    assert len(first_page.context["boletos"]) == 20
    assert first_page.context["page_obj"].paginator.num_pages == 2
    assert first_page.context["metrics"]["paid"] == 8
    assert first_page.context["metrics"]["pending"] == 15
    assert filtered.status_code == 200
    assert all(item.seller == sellers[0] for item in filtered.context["boletos"])
    assert all(item.status == BoletoStatus.PAID for item in filtered.context["boletos"])
    amounts = [item.amount_cents for item in filtered.context["boletos"]]
    assert amounts == sorted(amounts, reverse=True)
    assert list(no_match.context["boletos"]) == []
    assert malformed.status_code == 200


@pytest.mark.django_db
def test_seller_list_is_scoped_without_metrics(client, sellers, companies):
    own = make_boleto(
        seller=sellers[0],
        company=companies[0],
        index=1,
        status=BoletoStatus.PAID,
    )
    make_boleto(
        seller=sellers[1],
        company=companies[1],
        index=2,
        status=BoletoStatus.PENDING,
    )

    with patch("apps.sellers.middleware.get_seller_from_session", return_value=sellers[0]):
        response = client.get(reverse("boletos:seller_list"))

    assert response.status_code == 200
    assert list(response.context["boletos"]) == [own]
    assert "metrics" not in response.context
    assert b"boleto-metrics" not in response.content
    assert b"<dt>Vendedor</dt>" not in response.content


@pytest.mark.django_db
def test_manager_detail_has_technical_audit_and_seller_detail_does_not(
    client,
    manager,
    sellers,
    companies,
):
    boleto = make_boleto(seller=sellers[0], company=companies[0], index=1)
    WebhookEvent.objects.create(
        boleto=boleto,
        provider_event_id="hook_panel",
        event_type="order.paid",
        payload={"id": "hook_panel", "private_marker": "manager-only"},
        payload_sha256="0" * 64,
        authenticity_status="VERIFIED",
    )
    WhatsAppMessage.objects.create(
        seller=sellers[0],
        boleto=boleto,
        template_key="boleto_created_seller",
        event_type="boleto_created",
        recipient_phone=sellers[0].whatsapp_phone,
        rendered_text="Boleto emitido",
        sent_at=timezone.now(),
    )

    client.force_login(manager)
    manager_response = client.get(
        reverse("boletos:manager_detail", kwargs={"boleto_id": boleto.id})
    )
    client.logout()
    with patch("apps.sellers.middleware.get_seller_from_session", return_value=sellers[0]):
        seller_response = client.get(
            reverse("boletos:seller_detail", kwargs={"boleto_id": boleto.id})
        )

    assert manager_response.status_code == 200
    assert b"private_marker" in manager_response.content
    assert b"Eventos do Pagar.me" in manager_response.content
    assert seller_response.status_code == 200
    assert b"private_marker" not in seller_response.content
    assert b"Eventos do Pagar.me" not in seller_response.content
    assert b"Notifica" in seller_response.content
