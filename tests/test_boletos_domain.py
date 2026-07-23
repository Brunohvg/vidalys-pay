"""Domain and authorization tests for boletos."""
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.boletos.models import Boleto, BoletoStatus, Company
from apps.boletos.permissions import (
    BoletoActor,
    can_view_technical_data,
    resolve_creation_seller,
    scope_boletos,
)
from apps.sellers.models import Seller

pytestmark = pytest.mark.django_db


@pytest.fixture
def company():
    return Company.objects.create(
        cnpj="11222333000181",
        legal_name="Empresa Cliente Ltda",
        trade_name="Empresa Cliente",
        zip_code="01310100",
        street="Avenida Paulista",
        number="1000",
        district="Bela Vista",
        city="São Paulo",
        state="SP",
    )


@pytest.fixture
def seller():
    return Seller.objects.create(
        name="Vendedor Ativo",
        whatsapp_phone="+5511999999999",
        max_payment_amount_cents=1_000_000,
    )


@pytest.fixture
def other_seller():
    return Seller.objects.create(
        name="Outro Vendedor",
        whatsapp_phone="+5511888888888",
        max_payment_amount_cents=1_000_000,
    )


@pytest.fixture
def manager():
    return get_user_model().objects.create_superuser(
        username="gestor",
        email="gestor@example.com",
        password="test-password",
    )


def make_boleto(*, company, seller, idempotency_key, manager=None, creator_seller=None):
    return Boleto.objects.create(
        seller=seller,
        company=company,
        created_by_user=manager,
        created_by_seller=creator_seller,
        amount_cents=25_090,
        due_date=date(2026, 8, 15),
        description="Serviços contratados",
        internal_reference=f"REF-{idempotency_key}",
        idempotency_key=idempotency_key,
        company_snapshot={
            "cnpj": company.cnpj,
            "legal_name": company.legal_name,
            "address": {
                "zip_code": company.zip_code,
                "street": company.street,
                "number": company.number,
                "district": company.district,
                "city": company.city,
                "state": company.state,
            },
        },
    )


def test_company_normalizes_cnpj_before_validation():
    company = Company(
        cnpj="11.222.333/0001-81",
        legal_name="Empresa Normalizada",
        zip_code="01310100",
        street="Avenida Paulista",
        number="1000",
        district="Bela Vista",
        city="São Paulo",
        state="SP",
    )

    company.full_clean()

    assert company.cnpj == "11222333000181"


def test_company_cnpj_is_globally_unique(company):
    with pytest.raises(IntegrityError), transaction.atomic():
        Company.objects.create(
            cnpj=company.cnpj,
            legal_name="Empresa Duplicada",
            zip_code="01310100",
            street="Avenida Paulista",
            number="2000",
            district="Bela Vista",
            city="São Paulo",
            state="SP",
        )


def test_boleto_uses_cents_snapshot_and_initial_state(company, seller):
    boleto = make_boleto(
        company=company,
        seller=seller,
        creator_seller=seller,
        idempotency_key="seller-create-1",
    )

    assert boleto.amount_cents == 25_090
    assert boleto.status == BoletoStatus.CREATING
    assert boleto.company_snapshot["cnpj"] == company.cnpj
    assert boleto.created_by_seller == seller
    assert boleto.created_by_user is None


@pytest.mark.parametrize(
    ("manager_present", "seller_present"),
    [(False, False), (True, True)],
)
def test_boleto_requires_exactly_one_creator(
    company,
    seller,
    manager,
    manager_present,
    seller_present,
):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_boleto(
            company=company,
            seller=seller,
            manager=manager if manager_present else None,
            creator_seller=seller if seller_present else None,
            idempotency_key=f"invalid-actor-{manager_present}-{seller_present}",
        )


def test_seller_cannot_be_recorded_as_creator_for_another_seller(company, seller, other_seller):
    boleto = Boleto(
        seller=other_seller,
        company=company,
        created_by_seller=seller,
        amount_cents=10_000,
        due_date=date(2026, 8, 15),
        description="Cobrança",
        idempotency_key="wrong-seller",
        company_snapshot={},
    )

    with pytest.raises(ValidationError, match="só pode criar boletos para si"):
        boleto.full_clean()


def test_idempotency_is_unique_per_seller(company, seller):
    make_boleto(
        company=company,
        seller=seller,
        creator_seller=seller,
        idempotency_key="same-logical-attempt",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        make_boleto(
            company=company,
            seller=seller,
            creator_seller=seller,
            idempotency_key="same-logical-attempt",
        )


def test_same_idempotency_key_is_allowed_for_different_sellers(company, seller, other_seller):
    make_boleto(
        company=company,
        seller=seller,
        creator_seller=seller,
        idempotency_key="shared-client-key",
    )
    boleto = make_boleto(
        company=company,
        seller=other_seller,
        creator_seller=other_seller,
        idempotency_key="shared-client-key",
    )

    assert boleto.seller == other_seller


def test_manager_must_select_an_active_seller(manager, seller):
    actor = BoletoActor(user=manager)

    assert resolve_creation_seller(actor=actor, requested_seller=seller) == seller
    with pytest.raises(PermissionDenied, match="Selecione"):
        resolve_creation_seller(actor=actor)

    seller.is_active = False
    seller.save(update_fields=["is_active"])
    with pytest.raises(PermissionDenied, match="inativo"):
        resolve_creation_seller(actor=actor, requested_seller=seller)


def test_seller_is_automatically_bound_to_self(seller, other_seller):
    actor = BoletoActor(seller=seller)

    assert resolve_creation_seller(actor=actor) == seller
    assert resolve_creation_seller(actor=actor, requested_seller=seller) == seller
    with pytest.raises(PermissionDenied, match="outro vendedor"):
        resolve_creation_seller(actor=actor, requested_seller=other_seller)


def test_non_superuser_cannot_act_as_manager():
    user = get_user_model().objects.create_user(username="regular", password="test-password")
    actor = BoletoActor(user=user)

    with pytest.raises(PermissionDenied, match="não autorizado"):
        resolve_creation_seller(actor=actor)
    assert not can_view_technical_data(actor=actor)


def test_queryset_scope_separates_sellers(company, seller, other_seller, manager):
    own = make_boleto(
        company=company,
        seller=seller,
        creator_seller=seller,
        idempotency_key="own",
    )
    other = make_boleto(
        company=company,
        seller=other_seller,
        creator_seller=other_seller,
        idempotency_key="other",
    )

    seller_visible = scope_boletos(Boleto.objects.all(), actor=BoletoActor(seller=seller))
    manager_visible = scope_boletos(Boleto.objects.all(), actor=BoletoActor(user=manager))

    assert list(seller_visible) == [own]
    assert set(manager_visible) == {own, other}
    assert can_view_technical_data(actor=BoletoActor(user=manager))
    assert not can_view_technical_data(actor=BoletoActor(seller=seller))
