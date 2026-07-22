"""Tests for the freight module — Correios integration v2."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.freight.config import (
    DEFAULT_PRODUCTS,
    PACKAGE_PRESETS,
    PRODUCT_LABELS,
    REQUEST_TIMEOUT_SECONDS,
    CorreiosConfig,
    get_additional_delivery_days,
    get_correios_config,
    is_correios_configured,
)
from apps.freight.correios import (
    TOKEN_CACHE_KEY,
    CorreiosAuthClient,
    CorreiosFreightClient,
    calculate_token_ttl,
    parse_price_to_cents,
    resolve_dr,
)
from apps.freight.dataclasses import CEPAddressData, FreightOption, PackageData
from apps.freight.exceptions import (
    FreightAuthenticationError,
    FreightConnectionError,
    FreightProviderUnavailable,
    FreightTimeoutError,
)
from apps.freight.services import (
    _sort_options,
    format_price_cents,
    lookup_cep,
    validate_and_build_package,
)


# ── config ──────────────────────────────────────────────────────────────────


def test_config_only_six_fields():
    """Cartao is string, config has exactly 6 fields."""
    config = CorreiosConfig(
        usuario="user",
        codigo_acesso="secret",
        cartao_postagem="0074835858",
        contrato="9912464418",
        cnpj="31095761000106",
        cep_origem="30170130",
    )
    fields = [f.name for f in config.__dataclass_fields__.values()]
    assert fields == [
        "usuario", "codigo_acesso", "cartao_postagem",
        "contrato", "cnpj", "cep_origem",
    ]


def test_cartao_preserves_leading_zeros():
    config = CorreiosConfig(
        usuario="u", codigo_acesso="p", cartao_postagem="0074835858",
        contrato="", cnpj="", cep_origem="30170130",
    )
    assert config.cartao_postagem == "0074835858"
    assert isinstance(config.cartao_postagem, str)


def test_cartao_never_int():
    config = CorreiosConfig(
        usuario="u", codigo_acesso="p", cartao_postagem="0074835858",
        contrato="", cnpj="", cep_origem="30170130",
    )
    assert isinstance(config.cartao_postagem, str)
    assert config.cartao_postagem != "74835858"


def test_is_correios_configured_true():
    config = CorreiosConfig(
        usuario="u", codigo_acesso="p", cartao_postagem="",
        contrato="", cnpj="", cep_origem="30170130",
    )
    assert is_correios_configured(config) is True


def test_is_correios_configured_false():
    config = CorreiosConfig(
        usuario="", codigo_acesso="p", cartao_postagem="",
        contrato="", cnpj="", cep_origem="",
    )
    assert is_correios_configured(config) is False


# ── TTL ──────────────────────────────────────────────────────────────────────


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


# ── price parsing ────────────────────────────────────────────────────────────


def test_parse_price_integer():
    assert parse_price_to_cents(25) == 2500


def test_parse_price_float():
    assert parse_price_to_cents(25.50) == 2550


def test_parse_price_string_brl():
    assert parse_price_to_cents("25,50") == 2550


def test_parse_price_string_dot():
    assert parse_price_to_cents("25.50") == 2550


def test_parse_price_decimal():
    assert parse_price_to_cents(Decimal("25.50")) == 2550


def test_parse_price_zero():
    assert parse_price_to_cents("0") == 0


def test_parse_price_none():
    assert parse_price_to_cents(None) == 0


# ── format_price_cents ───────────────────────────────────────────────────────


def test_format_price_cents_100():
    assert format_price_cents(100) == "R$ 1,00"


def test_format_price_cents_2500():
    assert format_price_cents(2500) == "R$ 25,00"


# ── package validation ───────────────────────────────────────────────────────


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


# ── CEP lookup ───────────────────────────────────────────────────────────────


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
@patch("apps.freight.services._lookup_brasilapi", return_value=None)
def test_lookup_cep_not_found(mock_bp, mock_vp):
    result = lookup_cep("99999999")
    assert result is None


def test_lookup_cep_invalid_length():
    result = lookup_cep("123")
    assert result is None


# ── CEPAddressData ───────────────────────────────────────────────────────────


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


# ── FreightOption ────────────────────────────────────────────────────────────


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


# ── DR resolution ────────────────────────────────────────────────────────────


def test_resolve_dr_from_cartao_dr():
    token = {"cartaoPostagem": {"dr": "57"}}
    config = MagicMock(cnpj="", contrato="")
    assert resolve_dr(token, config, "") == "57"


def test_resolve_dr_from_cartao_nuDR():
    token = {"cartaoPostagem": {"nuDR": "99"}}
    config = MagicMock(cnpj="", contrato="")
    assert resolve_dr(token, config, "") == "99"


def test_resolve_dr_from_cartao_nuSe():
    token = {"cartaoPostagem": {"nuSe": "42"}}
    config = MagicMock(cnpj="", contrato="")
    assert resolve_dr(token, config, "") == "42"


def test_resolve_dr_from_contrato_nuSe():
    token = {"contrato": {"nuSe": "11"}}
    config = MagicMock(cnpj="", contrato="")
    assert resolve_dr(token, config, "") == "11"


def test_resolve_dr_fallback_empty():
    token = {}
    config = MagicMock(cnpj="", contrato="")
    assert resolve_dr(token, config, "") == ""


def test_resolve_dr_ignores_none():
    token = {"cartaoPostagem": {"dr": None, "nuDR": None, "nuSe": "36"}}
    config = MagicMock(cnpj="", contrato="")
    assert resolve_dr(token, config, "") == "36"


# ── auth client ──────────────────────────────────────────────────────────────


@patch("apps.freight.correios.get_correios_config")
def test_auth_url_without_cartao(mock_config):
    mock_config.return_value = CorreiosConfig(
        usuario="user", codigo_acesso="pass",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    client = CorreiosAuthClient()
    assert "cartaopostagem" not in client._token_url


@patch("apps.freight.correios.get_correios_config")
def test_auth_url_with_cartao(mock_config):
    mock_config.return_value = CorreiosConfig(
        usuario="user", codigo_acesso="pass",
        cartao_postagem="0074835858", contrato="", cnpj="", cep_origem="30170130",
    )
    client = CorreiosAuthClient()
    assert "cartaopostagem" in client._token_url


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_body_only_numero(mock_config, mock_post):
    """Cartao auth sends ONLY numero — no contrato, no DR."""
    mock_config.return_value = CorreiosConfig(
        usuario="user", codigo_acesso="pass",
        cartao_postagem="0074835858", contrato="9912464418",
        cnpj="31095761000106", cep_origem="30170130",
    )
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"token": "t", "expiraEm": 3600}
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    client._authenticate()

    body = mock_post.call_args.kwargs["json"]
    assert body == {"numero": "0074835858"}
    assert "contrato" not in body
    assert "dr" not in body
    assert "cnpj" not in body


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_body_none_without_cartao(mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="user", codigo_acesso="pass",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"token": "t", "expiraEm": 3600}
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    client._authenticate()

    assert mock_post.call_args.kwargs["json"] is None


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_uses_basic_auth(mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="arthur", codigo_acesso="sekrit",
        cartao_postagem="0074835858", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"token": "t", "expiraEm": 3600}
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    client._authenticate()

    auth_arg = mock_post.call_args.kwargs["auth"]
    assert isinstance(auth_arg, httpx.BasicAuth)


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_returns_token_data(mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "token": "my-bearer",
        "expiraEm": "2027-01-01T00:00:00Z",
        "cartaoPostagem": {"dr": "57"},
    }
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    data = client._authenticate()

    assert data["token"] == "my-bearer"
    assert "_expires_in" in data
    assert data["cartaoPostagem"]["dr"] == "57"


# ── cache ────────────────────────────────────────────────────────────────────


@patch("apps.freight.correios.cache")
@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_cache_stores_full_response(mock_config, mock_post, mock_cache):
    """Cache stores the full token dict, not just bearer string."""
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_cache.get.return_value = None
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "token": "t", "expiraEm": 3600,
        "cartaoPostagem": {"dr": "57"},
        "contrato": {"nuDR": "99"},
    }
    mock_post.return_value = mock_response

    client = CorreiosAuthClient()
    client.get_token_and_data()

    cached = mock_cache.set.call_args[0][1]
    assert cached["token"] == "t"
    assert cached["cartaoPostagem"]["dr"] == "57"
    assert cached["contrato"]["nuDR"] == "99"


@patch("apps.freight.correios.cache")
@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_token_renewed_on_401(mock_config, mock_post, mock_cache):
    """When _batch_price gets 401, token is invalidated and retried."""
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_cache.get.return_value = None

    # Auth succeeds
    mock_auth_response = MagicMock()
    mock_auth_response.raise_for_status.return_value = None
    mock_auth_response.json.return_value = {"token": "t1", "expiraEm": 3600}

    # First price call returns 401, second succeeds
    fail_resp = MagicMock()
    fail_resp.status_code = 401
    fail_resp.json.return_value = {}
    fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=fail_resp,
    )

    ok_resp = MagicMock()
    ok_resp.raise_for_status.return_value = None
    ok_resp.json.return_value = [{"coProduto": "03298", "pcFinal": "10,00"}]

    # Auth responses: first call, second call after invalidate
    mock_post.side_effect = [
        mock_auth_response,  # _authenticate first call
        mock_auth_response,  # _authenticate second call (after invalidate)
    ]

    client = CorreiosFreightClient()

    # Mock _batch_price to fail with 401 then succeed
    with patch.object(client, "_batch_price") as mock_price:
        mock_price.side_effect = [FreightAuthenticationError(), {"03298": 1000}]

        pkg = PackageData(
            destination_zip_code="30140071",
            weight_grams=100, length_cm="20",
            width_cm="15", height_cm="2",
        )
        with patch.object(client, "_batch_deadline", return_value={}):
            result = client.calculate(pkg)

    assert len(result) >= 1
    assert result[0].price_cents == 1000
    assert mock_price.call_count == 2


# ── product codes ────────────────────────────────────────────────────────────


def test_pac_code():
    assert PRODUCT_LABELS["03298"] == "PAC"


def test_sedex_code():
    assert PRODUCT_LABELS["03220"] == "SEDEX"


def test_default_products():
    assert DEFAULT_PRODUCTS == ["03298", "03220"]


# ── weight sent as grams string ──────────────────────────────────────────────


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
@patch("apps.freight.correios.CorreiosAuthClient.get_token_and_data")
def test_batch_price_weight_in_grams(mock_token, mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_token.return_value = {"token": "bearer"}
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [{"coProduto": "03298", "pcFinal": "10,00"}]
    mock_post.return_value = mock_response

    pkg = PackageData(
        destination_zip_code="30140071",
        weight_grams=300, length_cm="20",
        width_cm="15", height_cm="8",
    )

    client = CorreiosFreightClient()
    client._batch_price("bearer", pkg, "")

    payload = mock_post.call_args.kwargs["json"]
    ps_objeto = payload["parametrosProduto"][0]["psObjeto"]
    assert ps_objeto == "300"


# ── dimensions preserved from UI ─────────────────────────────────────────────


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
@patch("apps.freight.correios.CorreiosAuthClient.get_token_and_data")
def test_batch_price_dimensions_preserved(mock_token, mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_token.return_value = {"token": "bearer"}
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [{"coProduto": "03298", "pcFinal": "10,00"}]
    mock_post.return_value = mock_response

    pkg = PackageData(
        destination_zip_code="30140071",
        weight_grams=500, length_cm="25",
        width_cm="18", height_cm="12",
    )

    client = CorreiosFreightClient()
    client._batch_price("bearer", pkg, "")

    payload = mock_post.call_args.kwargs["json"]
    p = payload["parametrosProduto"][0]
    assert p["comprimento"] == "25"
    assert p["largura"] == "18"
    assert p["altura"] == "12"


# ── fallback dimensions used when empty ──────────────────────────────────────


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
@patch("apps.freight.correios.CorreiosAuthClient.get_token_and_data")
def test_batch_price_fallback_dims_on_empty(mock_token, mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_token.return_value = {"token": "bearer"}
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [{"coProduto": "03298", "pcFinal": "10,00"}]
    mock_post.return_value = mock_response

    pkg = PackageData(
        destination_zip_code="30140071",
        weight_grams=500, length_cm="", width_cm="", height_cm="",
    )

    client = CorreiosFreightClient()
    client._batch_price("bearer", pkg, "")

    payload = mock_post.call_args.kwargs["json"]
    p = payload["parametrosProduto"][0]
    assert p["comprimento"] == "20"
    assert p["largura"] == "20"
    assert p["altura"] == "20"


# ── deadline ─────────────────────────────────────────────────────────────────


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
@patch("apps.freight.correios.CorreiosAuthClient.get_token_and_data")
def test_deadline_uses_prazoEntrega(mock_token, mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_token.return_value = {"token": "bearer"}
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {"coProduto": "03298", "prazoEntrega": 5},
        {"coProduto": "03220", "prazoEntrega": 1},
    ]
    mock_post.return_value = mock_response

    pkg = PackageData(
        destination_zip_code="30140071",
        weight_grams=100, length_cm="20",
        width_cm="15", height_cm="2",
    )

    client = CorreiosFreightClient()
    result = client._batch_deadline("bearer", pkg)

    assert result["03298"] == 5
    assert result["03220"] == 1


# ── error messages (msgErro) ─────────────────────────────────────────────────


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
@patch("apps.freight.correios.CorreiosAuthClient.get_token_and_data")
def test_price_msgErro_skips_product(mock_token, mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_token.return_value = {"token": "bearer"}
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {"coProduto": "03298", "pcFinal": "10,00"},
        {"coProduto": "03220", "msgErro": "Servico indisponivel"},
    ]
    mock_post.return_value = mock_response

    pkg = PackageData(
        destination_zip_code="30140071",
        weight_grams=100, length_cm="20",
        width_cm="15", height_cm="2",
    )

    client = CorreiosFreightClient()
    result = client._batch_price("bearer", pkg, "")

    assert "03298" in result
    assert "03220" not in result


# ── error differentiation ────────────────────────────────────────────────────


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_401_raises_auth_error(mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    fail_resp = MagicMock()
    fail_resp.status_code = 401
    fail_resp.json.return_value = {}
    mock_post.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=fail_resp,
    )

    client = CorreiosAuthClient()
    with pytest.raises(FreightAuthenticationError):
        client._authenticate()


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
def test_auth_timeout_raises_timeout_error(mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_post.side_effect = httpx.TimeoutException("timeout")

    client = CorreiosAuthClient()
    with pytest.raises(FreightTimeoutError):
        client._authenticate()


@patch("apps.freight.correios.httpx.post")
@patch("apps.freight.correios.get_correios_config")
@patch("apps.freight.correios.CorreiosAuthClient.get_token_and_data")
def test_price_400_raises_specific_message(mock_token, mock_config, mock_post):
    mock_config.return_value = CorreiosConfig(
        usuario="u", codigo_acesso="p",
        cartao_postagem="", contrato="", cnpj="", cep_origem="30170130",
    )
    mock_token.return_value = {"token": "bearer"}
    fail_resp = MagicMock()
    fail_resp.status_code = 400
    fail_resp.json.return_value = {"message": "bad"}
    mock_post.side_effect = httpx.HTTPStatusError(
        "Bad Request", request=MagicMock(), response=fail_resp,
    )

    pkg = PackageData(
        destination_zip_code="30140071",
        weight_grams=100, length_cm="20",
        width_cm="15", height_cm="2",
    )

    client = CorreiosFreightClient()
    with pytest.raises(FreightProviderUnavailable) as exc_info:
        client._batch_price("bearer", pkg, "")
    assert "recusaram" in str(exc_info.value).lower()


# ── no _log_http_error anywhere ──────────────────────────────────────────────


def test_no_log_http_error_function():
    """_log_http_error must not exist."""
    import apps.freight.correios as corr
    assert not hasattr(corr, "_log_http_error")
    assert not hasattr(CorreiosAuthClient, "_log_http_error")
    assert not hasattr(CorreiosFreightClient, "_log_http_error")


# ── timeout constant ─────────────────────────────────────────────────────────


def test_timeout_is_constant():
    assert REQUEST_TIMEOUT_SECONDS == 10


# ── presets ──────────────────────────────────────────────────────────────────


def test_presets_contain_expected():
    names = [p["name"] for p in PACKAGE_PRESETS]
    assert "Envelope" in names
    assert "Caixa P" in names
    assert "Caixa M" in names
    assert "Caixa G" in names
    assert "Personalizado" in names


def test_personalizado_has_zero_values():
    pers = next(p for p in PACKAGE_PRESETS if p["name"] == "Personalizado")
    assert pers["weight_grams"] == 0
    assert pers["length_cm"] == 0
    assert pers["width_cm"] == 0
    assert pers["height_cm"] == 0


# ── additional delivery days ────────────────────────────────────────────────


def test_additional_days_default_zero(settings):
    if hasattr(settings, "CORREIOS_DIAS_ADICIONAIS"):
        delattr(settings, "CORREIOS_DIAS_ADICIONAIS")
    assert get_additional_delivery_days() == 0


def test_additional_days_one(settings):
    settings.CORREIOS_DIAS_ADICIONAIS = "1"
    assert get_additional_delivery_days() == 1


def test_additional_days_invalid_string(settings):
    settings.CORREIOS_DIAS_ADICIONAIS = "abc"
    assert get_additional_delivery_days() == 0


def test_additional_days_negative(settings):
    settings.CORREIOS_DIAS_ADICIONAIS = "-1"
    assert get_additional_delivery_days() == 0


# ── sort options ─────────────────────────────────────────────────────────────


def test_sort_cheapest_first():
    options = [
        {"service_name": "PAC", "price_cents": 2500, "delivery_days": 5},
        {"service_name": "SEDEX", "price_cents": 1500, "delivery_days": 2},
    ]
    sorted_opts = _sort_options(options)
    assert sorted_opts[0]["service_name"] == "SEDEX"
    assert sorted_opts[1]["service_name"] == "PAC"


def test_sort_same_price_uses_delivery():
    options = [
        {"service_name": "PAC", "price_cents": 1000, "delivery_days": 8},
        {"service_name": "SEDEX", "price_cents": 1000, "delivery_days": 3},
    ]
    sorted_opts = _sort_options(options)
    assert sorted_opts[0]["service_name"] == "SEDEX"
    assert sorted_opts[1]["service_name"] == "PAC"


def test_sort_null_delivery_last():
    options = [
        {"service_name": "PAC", "price_cents": 1000, "delivery_days": None},
        {"service_name": "SEDEX", "price_cents": 1000, "delivery_days": 3},
    ]
    sorted_opts = _sort_options(options)
    assert sorted_opts[0]["delivery_days"] == 3
    assert sorted_opts[1]["delivery_days"] is None


def test_sort_invalid_price_last():
    options = [
        {"service_name": "SEDEX", "price_cents": 0, "delivery_days": 1},
        {"service_name": "PAC", "price_cents": 1500, "delivery_days": 5},
    ]
    sorted_opts = _sort_options(options)
    assert sorted_opts[0]["service_name"] == "PAC"
    assert sorted_opts[1]["service_name"] == "SEDEX"


# ── API is_best_option ───────────────────────────────────────────────────────

from apps.freight import api as freight_api_module


@patch.object(freight_api_module, "calculate_freight")
@patch.object(freight_api_module, "lookup_cep")
@patch.object(freight_api_module, "validate_and_build_package")
def test_api_is_best_option_first(mock_validate, mock_cep, mock_calc):
    """First valid option gets is_best_option=true."""
    mock_cep.return_value = CEPAddressData(
        zip_code="30140071", street="Rua A", neighborhood="B",
        city="BH", state="MG",
    )
    from apps.freight.dataclasses import PackageData
    mock_validate.return_value = PackageData(
        destination_zip_code="30140071", weight_grams=500,
        length_cm="20", width_cm="15", height_cm="10",
    )
    mock_calc.return_value = [
        {"service_code": "03220", "service_name": "SEDEX", "price_cents": 1036,
         "provider_delivery_days": 2, "additional_delivery_days": 1,
         "delivery_days": 3, "official": True, "error": None, "provider": "correios"},
        {"service_code": "03298", "service_name": "PAC", "price_cents": 1627,
         "provider_delivery_days": 5, "additional_delivery_days": 1,
         "delivery_days": 6, "official": True, "error": None, "provider": "correios"},
    ]

    from rest_framework.test import APIRequestFactory, force_authenticate
    factory = APIRequestFactory()
    request = factory.post("/api/v1/freight/calculate/", {
        "destination_zip_code": "30140071",
        "weight_grams": 500,
        "length_cm": "20", "width_cm": "15", "height_cm": "10",
    }, format="json")

    from unittest.mock import MagicMock
    request.seller = MagicMock()
    request.seller.id = "test-id"

    response = freight_api_module.calculate_freight_view(request)

    assert response.status_code == 200
    options = response.data["data"]["options"]
    assert len(options) == 2
    assert options[0]["is_best_option"] is True
    assert options[1]["is_best_option"] is False


# ── delivery_days fields in API ──────────────────────────────────────────────


@patch.object(freight_api_module, "calculate_freight")
@patch.object(freight_api_module, "lookup_cep")
@patch.object(freight_api_module, "validate_and_build_package")
def test_api_includes_provider_and_additional_days(mock_validate, mock_cep, mock_calc):
    mock_cep.return_value = CEPAddressData(
        zip_code="30140071", street="Rua A", neighborhood="B",
        city="BH", state="MG",
    )
    from apps.freight.dataclasses import PackageData
    mock_validate.return_value = PackageData(
        destination_zip_code="30140071", weight_grams=300,
        length_cm="20", width_cm="15", height_cm="8",
    )
    mock_calc.return_value = [
        {"service_code": "03220", "service_name": "SEDEX", "price_cents": 1036,
         "provider_delivery_days": 2, "additional_delivery_days": 1,
         "delivery_days": 3, "official": True, "error": None, "provider": "correios"},
    ]

    from rest_framework.test import APIRequestFactory
    factory = APIRequestFactory()
    request = factory.post("/api/v1/freight/calculate/", {
        "destination_zip_code": "30140071",
        "weight_grams": 300,
        "length_cm": "20", "width_cm": "15", "height_cm": "8",
    }, format="json")
    request.seller = MagicMock()
    request.seller.id = "test-id"

    response = freight_api_module.calculate_freight_view(request)

    assert response.status_code == 200
    opt = response.data["data"]["options"][0]
    assert opt["provider_delivery_days"] == 2
    assert opt["additional_delivery_days"] == 1
    assert opt["delivery_days"] == 3


@patch.object(freight_api_module, "calculate_freight")
@patch.object(freight_api_module, "lookup_cep")
@patch.object(freight_api_module, "validate_and_build_package")
def test_api_null_delivery_stays_null(mock_validate, mock_cep, mock_calc):
    mock_cep.return_value = CEPAddressData(
        zip_code="30140071", street="Rua A", neighborhood="B",
        city="BH", state="MG",
    )
    from apps.freight.dataclasses import PackageData
    mock_validate.return_value = PackageData(
        destination_zip_code="30140071", weight_grams=300,
        length_cm="20", width_cm="15", height_cm="8",
    )
    mock_calc.return_value = [
        {"service_code": "03220", "service_name": "SEDEX", "price_cents": 1036,
         "provider_delivery_days": None, "additional_delivery_days": 0,
         "delivery_days": None, "official": True, "error": "Prazo indisponível", "provider": "correios"},
    ]

    from rest_framework.test import APIRequestFactory
    factory = APIRequestFactory()
    request = factory.post("/api/v1/freight/calculate/", {
        "destination_zip_code": "30140071",
        "weight_grams": 300,
        "length_cm": "20", "width_cm": "15", "height_cm": "8",
    }, format="json")
    request.seller = MagicMock()
    request.seller.id = "test-id"

    response = freight_api_module.calculate_freight_view(request)

    assert response.status_code == 200
    opt = response.data["data"]["options"][0]
    assert opt["provider_delivery_days"] is None
    assert opt["delivery_days"] is None


# ── env.example includes CORREIOS_DIAS_ADICIONAIS ─────────────────────────────


def test_dotenv_has_additional_days():
    import os
    path = os.path.join(os.path.dirname(__file__), "..", ".env.example")
    with open(path) as f:
        content = f.read()
    assert "CORREIOS_DIAS_ADICIONAIS" in content


# ── env examples ─────────────────────────────────────────────────────────────


def test_only_six_env_vars_in_dotenv_example():
    """Verify .env.example contains only the 6 required vars."""
    import os
    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        ".env.example",
    )
    with open(path) as f:
        content = f.read()

    needed = [
        "CORREIOS_USUARIO",
        "CORREIOS_CODIGO_ACESSO",
        "CORREIOS_CARTAO_POSTAGEM",
        "CORREIOS_CONTRATO",
        "CORREIOS_CNPJ",
        "CORREIOS_CEP_ORIGEM",
    ]
    for var in needed:
        assert var in content, f"{var} missing from .env.example"

    forbidden = [
        "CORREIOS_ENABLED",
        "CORREIOS_DR",
        "CORREIOS_PAC_PRODUCT_CODE",
        "CORREIOS_SEDEX_PRODUCT_CODE",
    ]
    for var in forbidden:
        assert var not in content, f"{var} should not be in .env.example"
