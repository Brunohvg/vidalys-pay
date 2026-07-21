"""Tests for payment link models."""
import pytest

from apps.payment_links.models import PaymentLink, PaymentLinkStatus
from apps.sellers.models import Seller


@pytest.mark.django_db
def test_payment_link_creation():
    seller = Seller.objects.create(
        name="Test Seller",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1000000,
    )
    link = PaymentLink.objects.create(
        seller=seller,
        reference="PED-001",
        amount_cents=35000,
        installments=3,
        idempotency_key="test-key-001",
    )
    assert link.pk is not None
    assert link.status == PaymentLinkStatus.CREATING
    assert link.installments == 3


@pytest.mark.django_db
def test_payment_link_str():
    seller = Seller.objects.create(
        name="Test Seller",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1000000,
    )
    link = PaymentLink(
        seller=seller,
        reference="PED-002",
        amount_cents=10000,
        installments=1,
        status=PaymentLinkStatus.ACTIVE,
        idempotency_key="test-key-002",
    )
    assert "PED-002" in str(link)
    assert "Ativo" in str(link)
