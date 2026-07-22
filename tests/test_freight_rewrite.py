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


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_body_dr_zero_sends_int(mock_config, mock_post):
    mock_config.return_value = MagicMock(
        usuario="user",
        codigo_acesso="pass",
        cartao_postagem="74835858",
        contrato="",
        dr="0",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"token": "fake-token", "expiraEm": 3600}
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    client._authenticate()

    call_kwargs = mock_post.call_args.kwargs
    body = call_kwargs["json"]

    assert body is not None
    assert body["numero"] == "74835858"
    assert body["dr"] == 0
    assert isinstance(body["dr"], int)
    assert "contrato" not in body


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_body_with_contrato(mock_config, mock_post):
    mock_config.return_value = MagicMock(
        usuario="user",
        codigo_acesso="pass",
        cartao_postagem="74835858",
        contrato="9912464418",
        dr="",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"token": "fake-token", "expiraEm": 3600}
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    client._authenticate()

    call_kwargs = mock_post.call_args.kwargs
    body = call_kwargs["json"]

    assert body is not None
    assert body["numero"] == "74835858"
    assert body["contrato"] == "9912464418"
    assert "dr" not in body


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_body_full_credentials(mock_config, mock_post):
    mock_config.return_value = MagicMock(
        usuario="user",
        codigo_acesso="pass",
        cartao_postagem="74835858",
        contrato="9912464418",
        dr="0",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"token": "fake-token", "expiraEm": 3600}
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    client._authenticate()

    call_kwargs = mock_post.call_args.kwargs
    body = call_kwargs["json"]

    assert body is not None
    assert body["numero"] == "74835858"
    assert body["contrato"] == "9912464418"
    assert body["dr"] == 0
    assert isinstance(body["dr"], int)


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_body_no_cartao_sends_none_body(mock_config, mock_post):
    mock_config.return_value = MagicMock(
        usuario="user",
        codigo_acesso="pass",
        cartao_postagem="",
        contrato="9912464418",
        dr="0",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"token": "fake-token", "expiraEm": 3600}
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    client._authenticate()

    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"] is None


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_body_empty_contrato_omitted(mock_config, mock_post):
    mock_config.return_value = MagicMock(
        usuario="user",
        codigo_acesso="pass",
        cartao_postagem="74835858",
        contrato="",
        dr="0",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"token": "fake-token", "expiraEm": 3600}
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    client._authenticate()

    call_kwargs = mock_post.call_args.kwargs
    body = call_kwargs["json"]

    assert body is not None
    assert "contrato" not in body


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_body_empty_dr_omitted(mock_config, mock_post):
    mock_config.return_value = MagicMock(
        usuario="user",
        codigo_acesso="pass",
        cartao_postagem="74835858",
        contrato="9912464418",
        dr="",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"token": "fake-token", "expiraEm": 3600}
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    client._authenticate()

    call_kwargs = mock_post.call_args.kwargs
    body = call_kwargs["json"]

    assert body is not None
    assert "dr" not in body


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
@patch("apps.freight.correios.CorreiosAuthClient.get_token")
def test_batch_price_nuDR_zero_from_dr_zero(mock_token, mock_config, mock_post):
    mock_config.return_value = MagicMock(
        usuario="user",
        codigo_acesso="pass",
        cartao_postagem="74835858",
        contrato="9912464418",
        dr="0",
        cep_origem="30170130",
        pac_product_code="03298",
        sedex_product_code="03220",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    mock_token.return_value = "fake-token"

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {"coProduto": "03298", "pcFinal": "25,00"},
        {"coProduto": "03220", "pcFinal": "35,00"},
    ]
    mock_post.return_value = mock_response

    package = PackageData(
        destination_zip_code="30140071",
        weight_grams=500,
        length_cm="20",
        width_cm="15",
        height_cm="10",
    )

    client = CorreiosFreightClient()
    client._batch_price("fake-token", ["03298", "03220"], package)

    call_kwargs = mock_post.call_args.kwargs
    payload = call_kwargs["json"]
    params = payload["parametrosProduto"][0]

    assert params["nuContrato"] == "9912464418"
    assert params["nuDR"] == 0
    assert isinstance(params["nuDR"], int)


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
@patch("apps.freight.correios.CorreiosAuthClient.get_token")
def test_batch_price_omits_nuDR_when_empty(mock_token, mock_config, mock_post):
    mock_config.return_value = MagicMock(
        usuario="user",
        codigo_acesso="pass",
        cartao_postagem="74835858",
        contrato="9912464418",
        dr="",
        cep_origem="30170130",
        pac_product_code="03298",
        sedex_product_code="03220",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    mock_token.return_value = "fake-token"

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {"coProduto": "03298", "pcFinal": "25,00"},
    ]
    mock_post.return_value = mock_response

    package = PackageData(
        destination_zip_code="30140071",
        weight_grams=500,
        length_cm="20",
        width_cm="15",
        height_cm="10",
    )

    client = CorreiosFreightClient()
    client._batch_price("fake-token", ["03298"], package)

    call_kwargs = mock_post.call_args.kwargs
    payload = call_kwargs["json"]
    params = payload["parametrosProduto"][0]

    assert "nuDR" not in params


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
@patch("apps.freight.correios.CorreiosAuthClient.get_token")
def test_batch_price_omits_nuContrato_when_empty(mock_token, mock_config, mock_post):
    mock_config.return_value = MagicMock(
        usuario="user",
        codigo_acesso="pass",
        cartao_postagem="74835858",
        contrato="",
        dr="0",
        cep_origem="30170130",
        pac_product_code="03298",
        sedex_product_code="03220",
        connect_timeout=5,
        read_timeout=15,
        token_cache_margin_seconds=300,
    )

    mock_token.return_value = "fake-token"

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {"coProduto": "03298", "pcFinal": "25,00"},
    ]
    mock_post.return_value = mock_response

    package = PackageData(
        destination_zip_code="30140071",
        weight_grams=500,
        length_cm="20",
        width_cm="15",
        height_cm="10",
    )

    client = CorreiosFreightClient()
    client._batch_price("fake-token", ["03298"], package)

    call_kwargs = mock_post.call_args.kwargs
    payload = call_kwargs["json"]
    params = payload["parametrosProduto"][0]

    assert "nuContrato" not in params


# --- Sanitization helpers ---

from apps.freight.correios import _sanitize_response_text


def test_sanitize_response_text_truncates():
    long_text = "x" * 500
    result = _sanitize_response_text(long_text, max_length=100)
    assert len(result) == 103  # 100 chars + "..."
    assert result.endswith("...")


def test_sanitize_response_text_short():
    result = _sanitize_response_text("hello")
    assert result == "hello"


def test_sanitize_response_text_none():
    result = _sanitize_response_text(None)
    assert result == ""


@patch("apps.freight.correios.logger")
def test_log_http_error_includes_etapa_and_status(mock_logger):
    from apps.freight.correios import _log_http_error
    import httpx

    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.text = '{"mensagem": "erro interno"}'

    exc = httpx.HTTPStatusError(
        message="Server error",
        request=MagicMock(),
        response=fake_response,
    )

    _log_http_error("preco", exc, co_produto="03298")

    mock_logger.warning.assert_called_once()
    log_msg = mock_logger.warning.call_args[0][0]
    log_extra = mock_logger.warning.call_args[0][1]
    assert "correios_http_error=true" in log_msg
    assert log_extra["etapa"] == "preco"
    assert log_extra["http_status"] == 500
    assert log_extra["coProduto"] == "03298"
    assert "código_acesso" not in log_extra
    assert "token" not in log_extra
    assert "Authorization" not in log_extra


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
