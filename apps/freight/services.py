"""Freight calculation business logic."""
import logging
import re
from decimal import Decimal, ROUND_HALF_UP

import httpx
from django.core.cache import cache

from .config import PACKAGE_PRESETS, get_additional_delivery_days, get_correios_config, is_correios_configured
from .correios import CorreiosFreightClient
from .dataclasses import CEPAddressData, FreightOption, PackageData
from .exceptions import (
    FreightAuthenticationError,
    FreightConfigurationError,
    FreightConnectionError,
    FreightError,
    FreightProviderUnavailable,
    FreightTimeoutError,
    FreightValidationError,
)

logger = logging.getLogger("apps.freight")

_FREIGHT_CACHE_TTL = 600
_CEP_CACHE_TTL = 604800  # 7 days
_CEP_RE = re.compile(r"^\d{8}$")


def get_package_presets() -> list[dict]:
    return PACKAGE_PRESETS


def validate_and_build_package(
    destination_zip_code: str,
    weight_grams: int,
    length_cm,
    width_cm,
    height_cm,
    declared_value_cents: int = 0,
) -> PackageData:
    errors: dict[str, str] = {}

    if not _CEP_RE.match(destination_zip_code or ""):
        errors["destination_zip_code"] = "CEP deve ter 8 dígitos."

    if not weight_grams or weight_grams <= 0:
        errors["weight_grams"] = "Peso deve ser maior que zero."
    elif weight_grams > 30000:
        errors["weight_grams"] = "Peso máximo: 30 kg."

    for field, value, max_val in [
        ("length_cm", length_cm, 105),
        ("width_cm", width_cm, 105),
        ("height_cm", height_cm, 105),
    ]:
        try:
            val = float(value) if value else 0
        except (TypeError, ValueError):
            val = 0
        if val <= 0:
            errors[field] = f"{field} deve ser maior que zero."
        elif val > max_val:
            errors[field] = f"{field} máximo: {max_val} cm."

    if declared_value_cents < 0:
        errors["declared_value_cents"] = "Valor declarado não pode ser negativo."

    if errors:
        raise FreightValidationError(errors)

    return PackageData(
        destination_zip_code=destination_zip_code,
        weight_grams=weight_grams,
        length_cm=str(length_cm),
        width_cm=str(width_cm),
        height_cm=str(height_cm),
        declared_value_cents=declared_value_cents,
    )


def _sort_options(options: list[dict]) -> list[dict]:
    """Sort freight options: cheapest first, then by delivery days."""
    def sort_key(opt: dict) -> tuple:
        price = opt.get("price_cents", 0) or 0
        has_valid = price > 0
        days = opt.get("delivery_days")
        return (
            0 if has_valid else 1,
            price if has_valid else float("inf"),
            days if days is not None else float("inf"),
        )

    return sorted(options, key=sort_key)


def calculate_freight(package: PackageData) -> list[FreightOption]:
    config = get_correios_config()

    if not is_correios_configured(config):
        raise FreightConfigurationError(
            "O cálculo de frete ainda não foi configurado."
        )

    cache_key = _build_cache_key(package, config)

    cached = cache.get(cache_key)
    if cached is not None:
        logger.info("Frete cache hit: cep=%s***", package.destination_zip_code[:5])
        return cached

    try:
        client = CorreiosFreightClient()
        options = client.calculate(package)
    except FreightConfigurationError:
        raise
    except FreightAuthenticationError as exc:
        logger.warning("frete_authentication_error=true cep=%s***", package.destination_zip_code[:5])
        raise FreightProviderUnavailable(str(exc)) from exc
    except FreightTimeoutError as exc:
        logger.warning("frete_timeout=true cep=%s***", package.destination_zip_code[:5])
        raise FreightProviderUnavailable(str(exc)) from exc
    except FreightConnectionError as exc:
        logger.warning("frete_connection_error=true cep=%s***", package.destination_zip_code[:5])
        raise FreightProviderUnavailable(str(exc)) from exc
    except FreightError:
        raise
    except Exception as exc:
        logger.exception("Erro inesperado ao calcular frete.")
        raise FreightProviderUnavailable(
            "Erro ao consultar os Correios. Tente novamente."
        ) from exc

    additional_days = get_additional_delivery_days()

    options_dicts = [
        {
            "provider": o.provider,
            "service_code": o.service_code,
            "service_name": o.service_name,
            "price_cents": o.price_cents,
            "provider_delivery_days": o.delivery_days,
            "additional_delivery_days": additional_days,
            "delivery_days": (
                o.delivery_days + additional_days
                if o.delivery_days is not None
                else None
            ),
            "official": o.official,
            "error": o.error,
        }
        for o in options
    ]

    options_dicts = _sort_options(options_dicts)

    cache.set(cache_key, options_dicts, timeout=_FREIGHT_CACHE_TTL)

    return options


def lookup_cep(zip_code: str) -> CEPAddressData | None:
    """Look up CEP address via ViaCEP with BrasilAPI fallback."""
    clean = re.sub(r"\D", "", zip_code or "")
    if len(clean) != 8:
        return None

    cache_key = f"freight:cep:{clean}"
    cached = cache.get(cache_key)
    if cached is not None:
        if isinstance(cached, dict):
            return CEPAddressData(**cached)
        return cached

    result = _lookup_viacep(clean)
    if result is None:
        result = _lookup_brasilapi(clean)

    if result is not None:
        cache.set(cache_key, result, timeout=_CEP_CACHE_TTL)

    return result


def _lookup_viacep(zip_code: str) -> CEPAddressData | None:
    url = f"https://viacep.com.br/ws/{zip_code}/json/"
    try:
        response = httpx.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
    except Exception:
        logger.debug("ViaCEP falhou para %s", zip_code)
        return None

    if data.get("erro"):
        return None

    return CEPAddressData(
        zip_code=zip_code,
        street=data.get("logradouro", ""),
        neighborhood=data.get("bairro", ""),
        city=data.get("localidade", ""),
        state=data.get("uf", ""),
        source="viacep",
    )


def _lookup_brasilapi(zip_code: str) -> CEPAddressData | None:
    url = f"https://brasilapi.com.br/api/cep/v1/{zip_code}"
    try:
        response = httpx.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
    except Exception:
        logger.debug("BrasilAPI falhou para %s", zip_code)
        return None

    if "erro" in data:
        return None

    return CEPAddressData(
        zip_code=zip_code,
        street=data.get("logradouro", ""),
        neighborhood=data.get("bairro", ""),
        city=data.get("cidade", "") or data.get("city", ""),
        state=data.get("estado", "") or data.get("state", ""),
        source="brasilapi",
    )


def format_price_cents(cents: int) -> str:
    """Format cents as BRL currency string."""
    value = Decimal(str(cents)) / Decimal("100")
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def _build_cache_key(package: PackageData, config) -> str:
    components = [
        config.cep_origem,
        package.destination_zip_code,
        str(package.weight_grams),
        str(package.length_cm),
        str(package.width_cm),
        str(package.height_cm),
        str(package.declared_value_cents),
    ]
    return f"freight:calc:{'|'.join(components)}"
