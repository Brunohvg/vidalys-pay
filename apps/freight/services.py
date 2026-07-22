"""Freight calculation business logic."""
import logging
import re
from decimal import Decimal

import httpx
from django.core.cache import cache

from .config import PACKAGE_PRESETS
from .correios import CorreiosFreightClient
from .dataclasses import FreightOption, PackageData
from .exceptions import (
    FreightConfigurationError,
    FreightError,
    FreightProviderUnavailable,
    FreightValidationError,
)

logger = logging.getLogger("apps.freight")

_FREIGHT_CACHE_TTL = 600
_CEP_CACHE_TTL = 604800
_CEP_RE = re.compile(r"^\d{8}$")


def get_package_presets() -> list[dict]:
    return PACKAGE_PRESETS


def validate_and_build_package(
    destination_zip_code: str,
    weight_grams: int,
    length_cm: Decimal,
    width_cm: Decimal,
    height_cm: Decimal,
    declared_value_cents: int = 0,
) -> PackageData:
    errors: dict[str, str] = {}

    if not _CEP_RE.match(destination_zip_code or ""):
        errors["destination_zip_code"] = "CEP deve ter 8 digitos."

    if not weight_grams or weight_grams <= 0:
        errors["weight_grams"] = "Peso deve ser maior que zero."
    elif weight_grams > 30000:
        errors["weight_grams"] = "Peso maximo: 30 kg."

    for field, value, max_val in [
        ("length_cm", length_cm, 105),
        ("width_cm", width_cm, 105),
        ("height_cm", height_cm, 105),
    ]:
        if not value or float(value) <= 0:
            errors[field] = f"{field} deve ser maior que zero."
        elif float(value) > max_val:
            errors[field] = f"{field} maximo: {max_val} cm."

    if declared_value_cents < 0:
        errors["declared_value_cents"] = "Valor declarado nao pode ser negativo."

    if errors:
        raise FreightValidationError(errors)

    return PackageData(
        destination_zip_code=destination_zip_code,
        weight_grams=weight_grams,
        length_cm=length_cm,
        width_cm=width_cm,
        height_cm=height_cm,
        declared_value_cents=declared_value_cents,
    )


def calculate_freight(package: PackageData) -> list[FreightOption]:
    from .config import get_correios_config

    config = get_correios_config()

    if not config.enabled:
        raise FreightConfigurationError(
            "O calculo de frete ainda nao esta configurado."
        )

    cache_key = _build_cache_key(package)

    cached = cache.get(cache_key)
    if cached is not None:
        logger.info("Frete cache hit: cep=%s***", package.destination_zip_code[:5])
        return [
            FreightOption(**opt) if isinstance(opt, dict) else opt
            for opt in cached
        ]

    try:
        client = CorreiosFreightClient()
        options = client.calculate(package)
    except FreightConfigurationError:
        raise
    except FreightError:
        raise
    except Exception as exc:
        logger.exception("Erro inesperado ao calcular frete.")
        raise FreightProviderUnavailable(
            "Erro ao consultar os Correios. Tente novamente."
        ) from exc

    options_dicts = [
        {
            "provider": o.provider,
            "service_code": o.service_code,
            "service_name": o.service_name,
            "price_cents": o.price_cents,
            "delivery_days": o.delivery_days,
            "official": o.official,
            "error": o.error,
        }
        for o in options
    ]

    cache.set(cache_key, options_dicts, timeout=_FREIGHT_CACHE_TTL)

    return options


def lookup_cep(zip_code: str) -> dict | None:
    cache_key = f"freight:cep:{zip_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"https://viacep.com.br/ws/{zip_code}/json/"
    try:
        response = httpx.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    if data.get("erro"):
        return None

    result = {
        "zip_code": zip_code,
        "city": data.get("localidade", ""),
        "state": data.get("uf", ""),
        "neighborhood": data.get("bairro", ""),
        "street": data.get("logradouro", ""),
    }

    cache.set(cache_key, result, timeout=_CEP_CACHE_TTL)
    return result


def format_price_cents(cents: int) -> str:
    return f"R$ {cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_cache_key(package: PackageData) -> str:
    from .config import get_correios_config

    config = get_correios_config()
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
