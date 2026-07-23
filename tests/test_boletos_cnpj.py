"""CNPJ validation, BrasilAPI gateway and endpoint tests."""
from unittest.mock import patch

import httpx
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.boletos.gateways.cnpj_provider import (
    BrasilApiCnpjGateway,
    CnpjNotFoundError,
    CnpjProviderTimeoutError,
    CnpjProviderUnavailableError,
)
from apps.boletos.services.cnpj_lookup import CompanyLookupResult, lookup_company
from apps.boletos.validators import is_valid_cnpj, normalize_cnpj, validate_cnpj
from apps.sellers.models import Seller

VALID_CNPJ = "11222333000181"
MASKED_CNPJ = "11.222.333/0001-81"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (MASKED_CNPJ, VALID_CNPJ),
        (VALID_CNPJ, VALID_CNPJ),
        ("CNPJ 11.222.333/0001-81", VALID_CNPJ),
        (None, ""),
    ],
)
def test_normalize_cnpj(raw, expected):
    assert normalize_cnpj(raw) == expected


@pytest.mark.parametrize(
    "cnpj",
    [
        "",
        "12345678901",
        "11111111111111",
        "11222333000180",
        "52998224725",
    ],
)
def test_invalid_cnpj_is_rejected(cnpj):
    assert not is_valid_cnpj(cnpj)
    with pytest.raises(ValidationError):
        validate_cnpj(cnpj)


def test_masked_valid_cnpj_is_accepted():
    assert is_valid_cnpj(MASKED_CNPJ)
    validate_cnpj(MASKED_CNPJ)


def test_lookup_company_maps_complete_brasilapi_response():
    gateway = type(
        "Gateway",
        (),
        {
            "lookup": lambda self, cnpj: {
                "razao_social": "EMPRESA CLIENTE LTDA",
                "nome_fantasia": "EMPRESA CLIENTE",
                "descricao_tipo_de_logradouro": "AVENIDA",
                "logradouro": "PAULISTA",
                "numero": "1000",
                "complemento": None,
                "bairro": "BELA VISTA",
                "municipio": "SAO PAULO",
                "uf": "sp",
                "cep": "01310-100",
                "email": "financeiro@example.com",
                "ddd_telefone_1": "1133334444",
                "descricao_situacao_cadastral": "ATIVA",
            }
        },
    )()

    result = lookup_company(MASKED_CNPJ, gateway=gateway)

    assert result == CompanyLookupResult(
        cnpj=VALID_CNPJ,
        legal_name="EMPRESA CLIENTE LTDA",
        trade_name="EMPRESA CLIENTE",
        email="financeiro@example.com",
        phone="1133334444",
        zip_code="01310100",
        street="AVENIDA PAULISTA",
        number="1000",
        district="BELA VISTA",
        city="SAO PAULO",
        state="SP",
        registration_status="ATIVA",
    )


def test_lookup_company_tolerates_missing_optional_fields():
    gateway = type("Gateway", (), {"lookup": lambda self, cnpj: {"razao_social": "EMPRESA"}})()

    result = lookup_company(VALID_CNPJ, gateway=gateway)

    assert result.legal_name == "EMPRESA"
    assert result.trade_name == ""
    assert result.street == ""
    assert result.email == ""


def test_invalid_cnpj_does_not_call_provider():
    class Gateway:
        called = False

        def lookup(self, cnpj):
            self.called = True
            return {}

    gateway = Gateway()
    with pytest.raises(ValidationError):
        lookup_company("123", gateway=gateway)
    assert not gateway.called


def make_http_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gateway_uses_configured_endpoint_headers_and_timeout(settings):
    settings.CNPJ_LOOKUP_BASE_URL = "https://provider.example/api/cnpj/v1"
    captured = {}

    def handler(request):
        captured["request"] = request
        return httpx.Response(200, json={"razao_social": "EMPRESA"})

    gateway = BrasilApiCnpjGateway(client=make_http_client(handler))
    payload = gateway.lookup(VALID_CNPJ)

    assert payload["razao_social"] == "EMPRESA"
    assert str(captured["request"].url).endswith(f"/{VALID_CNPJ}")
    assert captured["request"].headers["user-agent"] == settings.CNPJ_LOOKUP_USER_AGENT


@pytest.mark.parametrize(
    ("response", "exception"),
    [
        (httpx.Response(404, json={}), CnpjNotFoundError),
        (httpx.Response(503, json={}), CnpjProviderUnavailableError),
        (httpx.Response(200, text="not-json"), CnpjProviderUnavailableError),
    ],
)
def test_gateway_maps_provider_failures(response, exception):
    gateway = BrasilApiCnpjGateway(client=make_http_client(lambda request: response))

    with pytest.raises(exception):
        gateway.lookup(VALID_CNPJ)


def test_gateway_maps_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    gateway = BrasilApiCnpjGateway(client=make_http_client(handler))

    with pytest.raises(CnpjProviderTimeoutError):
        gateway.lookup(VALID_CNPJ)


@pytest.fixture
def manager(db):
    return get_user_model().objects.create_superuser(
        username="cnpj-manager",
        email="manager@example.com",
        password="test-password",
    )


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="Vendedor CNPJ",
        whatsapp_phone="+5511999999999",
        max_payment_amount_cents=1_000_000,
    )


def lookup_url(cnpj=VALID_CNPJ):
    return reverse("boletos_api:lookup_cnpj", kwargs={"cnpj": cnpj})


@pytest.mark.django_db
def test_lookup_endpoint_requires_authentication(client):
    response = client.get(lookup_url())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.django_db
def test_manager_can_lookup_cnpj(client, manager):
    client.force_login(manager)
    result = CompanyLookupResult(cnpj=VALID_CNPJ, legal_name="EMPRESA")

    with patch("apps.boletos.api.lookup_company", return_value=result) as lookup:
        response = client.get(lookup_url())

    assert response.status_code == 200
    assert response.json()["data"]["legal_name"] == "EMPRESA"
    lookup.assert_called_once_with(VALID_CNPJ)


@pytest.mark.django_db
def test_active_seller_can_lookup_cnpj(client, seller):
    result = CompanyLookupResult(cnpj=VALID_CNPJ, legal_name="EMPRESA")

    with (
        patch("apps.sellers.middleware.get_seller_from_session", return_value=seller),
        patch("apps.boletos.api.lookup_company", return_value=result),
    ):
        response = client.get(lookup_url())

    assert response.status_code == 200


@pytest.mark.django_db
def test_inactive_seller_cannot_lookup_cnpj(client, seller):
    seller.is_active = False
    seller.save(update_fields=["is_active"])

    with patch("apps.sellers.middleware.get_seller_from_session", return_value=seller):
        response = client.get(lookup_url())

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("exception", "status_code", "error_code"),
    [
        (CnpjNotFoundError(), 404, "not_found"),
        (CnpjProviderTimeoutError(), 504, "provider_timeout"),
        (CnpjProviderUnavailableError(), 503, "provider_unavailable"),
    ],
)
def test_lookup_endpoint_returns_safe_provider_errors(
    client,
    manager,
    exception,
    status_code,
    error_code,
):
    client.force_login(manager)

    with patch("apps.boletos.api.lookup_company", side_effect=exception):
        response = client.get(lookup_url())

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == error_code


@pytest.mark.django_db
def test_lookup_endpoint_rejects_invalid_cnpj_before_provider(client, manager):
    client.force_login(manager)

    response = client.get(lookup_url("123"))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_cnpj"


@pytest.mark.django_db
def test_lookup_endpoint_is_rate_limited(client, manager):
    cache.clear()
    client.force_login(manager)
    result = CompanyLookupResult(cnpj=VALID_CNPJ, legal_name="EMPRESA")

    with patch("apps.boletos.api.lookup_company", return_value=result):
        responses = [client.get(lookup_url()) for _ in range(21)]

    assert responses[-1].status_code == 429
    assert responses[-1].json()["error"]["code"] == "rate_limit_exceeded"
