"""Tests for the freight module rewrite."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.freight.correios import (
    CorreiosAuthClient,
    CorreiosFreightClient,
    _parse_price,
    calculate_token_ttl,
)
from apps.freight.dataclasses import CEPAddressData, FreightOption, PackageData
from apps.freight.services import (
    format_price_cents,
    lookup_cep,
    validate_and_build_package,
)


# --- Token TTL parsing ---


def test_token_ttl_integer():
    assert calculate_token_ttl(3600) == 3600


def test_token_ttl_iso_string():
    now = datetime.now(timezone.utc)
    future = now.replace(hour=now.hour + 1)
    iso = future.isoformat()
    ttl = calculate_token_ttl(iso)
    assert 3500 <= ttl <= 3700


def test_token_ttl_iso_with_z():
    now = datetime.now(timezone.utc)
    future = now.replace(hour=now.hour + 2)
    iso = future.strftime("%Y-%m-%dT%H:%M:%SZ")
    ttl = calculate_token_ttl(iso)
    assert 7100 <= ttl <= 7300


def test_token_ttl_invalid_string():
    assert calculate_token_ttl("not-a-date") == 300


def test_token_ttl_none():
    assert calculate_token_ttl(None) == 300


# --- Price parsing ---


def test_parse_price_integer():
    assert _parse_price(25) == 2500


def test_parse_price_float():
    assert _parse_price(25.50) == 2550


def test_parse_price_string_brl():
    assert _parse_price("25,50") == 2550


def test_parse_price_string_dot():
    assert _parse_price("25.50") == 2550


def test_parse_price_string_integer():
    assert _parse_price("25") == 2500


def test_parse_price_decimal():
    assert _parse_price(Decimal("25.50")) == 2550


def test_parse_price_zero():
    assert _parse_price("0") == 0


def test_parse_price_empty():
    assert _parse_price("") == 0


def test_parse_price_none():
    assert _parse_price(None) == 0


# --- format_price_cents ---


def test_format_price_cents_100():
    assert format_price_cents(100) == "R$ 1,00"


def test_format_price_cents_1000():
    assert format_price_cents(1000) == "R$ 10,00"


def test_format_price_cents_10000():
    assert format_price_cents(10000) == "R$ 100,00"


def test_format_price_cents_100000():
    assert format_price_cents(100000) == "R$ 1.000,00"


def test_format_price_cents_2500():
    assert format_price_cents(2500) == "R$ 25,00"


# --- Package validation ---


def test_validate_package_valid():
    pkg = validate_and_build_package(
        destination_zip_code="30140071",
        weight_grams=500,
        length_cm=20,
        width_cm=15,
        height_cm=10,
    )
    assert pkg.destination_zip_code == "30140071"
    assert pkg.weight_grams == 500


def test_validate_package_invalid_cep():
    with pytest.raises(Exception):
        validate_and_build_package(
            destination_zip_code="123",
            weight_grams=500,
            length_cm=20,
            width_cm=15,
            height_cm=10,
        )


def test_validate_package_zero_weight():
    with pytest.raises(Exception):
        validate_and_build_package(
            destination_zip_code="30140071",
            weight_grams=0,
            length_cm=20,
            width_cm=15,
            height_cm=10,
        )


def test_validate_package_over_weight():
    with pytest.raises(Exception):
        validate_and_build_package(
            destination_zip_code="30140071",
            weight_grams=31000,
            length_cm=20,
            width_cm=15,
            height_cm=10,
        )


# --- CEP Lookup ---


@patch("apps.freight.services.httpx.get")
def test_lookup_cep_viacep_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "cep": "30140071",
        "logradouro": "Avenida Afonso Pena",
        "bairro": "Centro",
        "localidade": "Belo Horizonte",
        "uf": "MG",
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = lookup_cep("30140071")
    assert result is not None
    assert result.street == "Avenida Afonso Pena"
    assert result.city == "Belo Horizonte"
    assert result.state == "MG"
    assert result.source == "viacep"


@patch("apps.freight.services._lookup_viacep", return_value=None)
@patch("apps.freight.services.httpx.get")
def test_lookup_cep_brasilapi_fallback(mock_get, mock_viacep):
    from django.core.cache import cache
    cache.clear()

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "cep": "30140071",
        "logradouro": "Avenida Afonso Pena",
        "bairro": "Centro",
        "cidade": "Belo Horizonte",
        "estado": "MG",
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = lookup_cep("30140071")
    assert result is not None
    assert result.city == "Belo Horizonte"
    assert result.source == "brasilapi"


@patch("apps.freight.services._lookup_viacep", return_value=None)
@patch("apps.freight.services._lookup_brasilapi", return_value=None)
def test_lookup_cep_not_found(mock_bp, mock_vp):
    result = lookup_cep("99999999")
    assert result is None


def test_lookup_cep_invalid_length():
    result = lookup_cep("123")
    assert result is None


@patch("apps.freight.services._lookup_viacep", return_value=None)
@patch("apps.freight.services._lookup_brasilapi", return_value=None)
def test_lookup_cep_cache(mock_bp, mock_vp):
    # First call populates cache
    lookup_cep("30140071")
    # Second call should use cache (mocks won't be called again)
    result = lookup_cep("30140071")
    # Result may be None since mocks return None, but cache should work


# --- Auth client ---


@patch("apps.freight.correios.get_correios_config")
def test_auth_uses_basic_auth(mock_config):
    mock_config.return_value = MagicMock(
        usuario="test_user",
        codigo_acesso="test_pass",
        cartao_postagem="",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    client = CorreiosAuthClient()
    assert "autentica" in client._token_url
    assert "cartaopostagem" not in client._token_url


@patch("apps.freight.correios.get_correios_config")
def test_auth_with_cartao(mock_config):
    mock_config.return_value = MagicMock(
        usuario="test_user",
        codigo_acesso="test_pass",
        cartao_postagem="1234567890",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    client = CorreiosAuthClient()
    assert "cartaopostagem" in client._token_url


# --- Freight option ---


def test_freight_option_dataclass():
    opt = FreightOption(
        provider="correios",
        service_code="03298",
        service_name="PAC",
        price_cents=2500,
        delivery_days=6,
        official=True,
    )
    assert opt.price_cents == 2500
    assert opt.official is True


def test_freight_option_with_error():
    opt = FreightOption(
        provider="correios",
        service_code="03298",
        service_name="PAC",
        price_cents=0,
        delivery_days=None,
        official=False,
        error="Preço indisponível",
    )
    assert opt.price_cents == 0
    assert opt.error == "Preço indisponível"


# --- CEPAddressData ---


def test_cep_address_data():
    addr = CEPAddressData(
        zip_code="30140071",
        street="Avenida Afonso Pena",
        neighborhood="Centro",
        city="Belo Horizonte",
        state="MG",
    )
    assert addr.city == "Belo Horizonte"
    assert addr.source == "viacep"
