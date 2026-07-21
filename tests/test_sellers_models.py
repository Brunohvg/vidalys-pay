"""Tests for seller models."""
import pytest

from apps.sellers.models import Seller


@pytest.mark.django_db
def test_seller_creation():
    seller = Seller.objects.create(
        name="Bruno Vendas",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1000000,
    )
    assert seller.pk is not None
    assert seller.is_active is True
    assert str(seller) == "Bruno Vendas"


@pytest.mark.django_db
def test_seller_str():
    seller = Seller(name="Maria Silva", whatsapp_phone="+5511988887777", max_payment_amount_cents=500000)
    assert str(seller) == "Maria Silva"
