"""Tests for seller DRF authentication — fixing the auth layer blocking sellers."""
from unittest.mock import patch

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client
from django.urls import reverse

from apps.sellers.authentication import SellerPrincipal, SellerSessionAuthentication
from apps.sellers.models import Seller, SellerSession
from apps.sellers.services import generate_invitation


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="Seller Test",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1000000,
        is_active=True,
    )


@pytest.fixture
def inactive_seller(db):
    return Seller.objects.create(
        name="Seller Inativo",
        whatsapp_phone="+5531888888888",
        max_payment_amount_cents=500000,
        is_active=False,
    )


def _activate_seller(client, seller):
    """Helper: activate a seller session via invitation flow."""
    _, raw_token = generate_invitation(seller=seller)
    # GET activation page
    client.get(reverse("sellers:activate", kwargs={"token": raw_token}))
    # POST confirmation
    token = raw_token
    confirm_url = reverse("sellers:confirm_activation", kwargs={"token": token})
    client.post(confirm_url, follow=False)
    return client


@pytest.mark.django_db
class TestSellerSessionAuthentication:
    """Test the SellerSessionAuthentication DRF auth class."""

    def test_authenticate_returns_seller_principal(self, seller):
        auth = SellerSessionAuthentication()

        class FakeRequest:
            def __init__(self, seller):
                self._request = type("R", (), {"seller": seller})()

        request = FakeRequest(seller)
        result = auth.authenticate(request)

        assert result is not None
        principal, seller_obj = result
        assert isinstance(principal, SellerPrincipal)
        assert principal.is_authenticated is True
        assert principal.is_anonymous is False
        assert seller_obj == seller

    def test_authenticate_returns_none_when_no_seller(self):
        auth = SellerSessionAuthentication()

        class FakeRequest:
            _request = type("R", (), {"seller": None})()

        result = auth.authenticate(FakeRequest())
        assert result is None

    def test_authenticate_rejects_inactive_seller(self, inactive_seller):
        from rest_framework.exceptions import AuthenticationFailed

        auth = SellerSessionAuthentication()

        class FakeRequest:
            def __init__(self, seller):
                self._request = type("R", (), {"seller": seller})()

        with pytest.raises(AuthenticationFailed) as exc_info:
            auth.authenticate(FakeRequest(inactive_seller))

        assert "seller_not_authenticated" in str(exc_info.value.detail)

    def test_authenticate_header(self):
        auth = SellerSessionAuthentication()

        class FakeRequest:
            pass

        assert auth.authenticate_header(FakeRequest()) == "Session"


@pytest.mark.django_db
class TestCreatePaymentLinkAuth:
    """Test that create_payment_link_view works with seller session."""

    def test_seller_session_creates_link(self, client, seller):
        """Seller with valid session can create a payment link."""
        _activate_seller(client, seller)

        with patch("apps.payment_links.use_cases.PagarmeClient") as mock_client:
            mock_instance = mock_client.return_value
            mock_instance.create_payment_link.return_value = {
                "id": "pay_abc123",
                "url": "https://pagar.me/link/abc123",
                "status": "active",
            }

            response = client.post(
                reverse("payment_links_api:create"),
                data={
                    "reference": "PED-001",
                    "amount_cents": 10000,
                    "installments": 1,
                },
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY="test-key-001",
                HTTP_ACCEPT="application/json",
            )

            assert response.status_code in (201, 202)
            data = response.json()
            assert "data" in data
            assert data["data"]["reference"] == "PED-001"
            mock_instance.create_payment_link.assert_called_once()

    def test_no_session_returns_401(self, client):
        """Without seller session, API returns standardized 401."""
        response = client.post(
            reverse("payment_links_api:create"),
            data={
                "reference": "PED-002",
                "amount_cents": 10000,
                "installments": 1,
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="test-key-002",
            HTTP_ACCEPT="application/json",
        )

        assert response.status_code == 401
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "seller_not_authenticated"
        assert "Sua sessão" in data["error"]["message"]
        # Ensure no ErrorDetail objects leak
        assert isinstance(data["error"]["message"], str)

    def test_anonymous_user_doesnt_block_seller(self, client, seller):
        """request.user being AnonymousUser doesn't block authenticated seller."""
        _activate_seller(client, seller)

        with patch("apps.payment_links.use_cases.PagarmeClient") as mock_client:
            mock_instance = mock_client.return_value
            mock_instance.create_payment_link.return_value = {
                "id": "pay_xyz789",
                "url": "https://pagar.me/link/xyz789",
                "status": "active",
            }

            response = client.post(
                reverse("payment_links_api:create"),
                data={
                    "reference": "PED-003",
                    "amount_cents": 5000,
                    "installments": 1,
                },
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY="test-key-003",
                HTTP_ACCEPT="application/json",
            )

            assert response.status_code in (201, 202)


@pytest.mark.django_db
class TestFreightCalculationAuth:
    """Test that freight calculation works with seller session."""

    def test_freight_works_with_seller_session(self, client, seller):
        """Freight calculation endpoint works with valid seller session."""
        _activate_seller(client, seller)

        with patch("apps.freight.api.calculate_freight") as mock_calc:
            from apps.freight.services import FreightOption

            mock_calc.return_value = [
                FreightOption(
                    service_code="03298",
                    service_name="PAC",
                    price_cents=1500,
                    delivery_days=10,
                    official=True,
                    error=None,
                )
            ]

            with patch("apps.freight.api.lookup_cep") as mock_cep:
                mock_cep.return_value = {
                    "zip_code": "30130000",
                    "city": "Belo Horizonte",
                    "state": "MG",
                }

                response = client.post(
                    reverse("freight:calculate_freight"),
                    data={
                        "destination_zip_code": "30130-000",
                        "weight_grams": 500,
                        "length_cm": 20,
                        "width_cm": 15,
                        "height_cm": 10,
                        "declared_value_cents": 10000,
                    },
                    content_type="application/json",
                    HTTP_ACCEPT="application/json",
                )

                assert response.status_code == 200
                data = response.json()
                assert "data" in data
                assert data["data"]["options"][0]["service_name"] == "PAC"

    def test_freight_no_session_returns_401(self, client):
        """Without seller session, freight endpoint returns 401."""
        response = client.post(
            reverse("freight:calculate_freight"),
            data={
                "destination_zip_code": "30130-000",
                "weight_grams": 500,
                "length_cm": 20,
                "width_cm": 15,
                "height_cm": 10,
            },
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "seller_not_authenticated"


@pytest.mark.django_db
class TestEndpointNotPublic:
    """Verify endpoints are not publicly accessible."""

    def test_create_link_requires_auth(self, client):
        """Create payment link endpoint is not public."""
        response = client.post(
            reverse("payment_links_api:create"),
            data={"reference": "TEST", "amount_cents": 1000},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="key-123",
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 401

    def test_freight_requires_auth(self, client):
        """Freight calculation endpoint is not public."""
        response = client.post(
            reverse("freight:calculate_freight"),
            data={"destination_zip_code": "30130000"},
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestInactiveSellerRejected:
    """Verify inactive sellers are rejected."""

    def test_inactive_seller_gets_401(self, client, inactive_seller):
        """Inactive seller session returns 401."""
        # Manually create a session for the inactive seller
        session = SessionStore()
        session["seller_id"] = str(inactive_seller.id)
        session.create()

        SellerSession.objects.create(
            seller=inactive_seller,
            django_session_key=session.session_key,
            expires_at="2099-01-01T00:00:00Z",
        )

        # Set the session cookie
        client.cookies["vidalys_seller_session"] = session.session_key

        response = client.post(
            reverse("payment_links_api:create"),
            data={"reference": "TEST", "amount_cents": 1000},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="key-inactive",
            HTTP_ACCEPT="application/json",
        )

        # The middleware sets request.seller = None for inactive sellers
        # So the endpoint should return 401
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "seller_not_authenticated"
