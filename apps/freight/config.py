"""Centralized Correios configuration."""
from dataclasses import dataclass

from django.conf import settings

from .exceptions import FreightConfigurationError

_CEP_REQUIRED_MESSAGE = "CEP de origem dos Correios precisa ter 8 digitos."
_PLACEHOLDER_PATTERNS = ("configure-no", "troque", "seu-", "gere-um")


@dataclass(frozen=True)
class CorreiosConfig:
    enabled: bool
    usuario: str
    codigo_acesso: str
    cartao_postagem: str
    contrato: str
    dr: str
    cnpj: str
    cep_origem: str
    pac_product_code: str
    sedex_product_code: str
    connect_timeout: float
    read_timeout: float
    token_cache_margin_seconds: int
    allow_estimate_fallback: bool
    default_length_cm: int
    default_width_cm: int
    default_height_cm: int


def get_correios_config() -> CorreiosConfig:
    """Build CorreiosConfig from Django settings.

    Validates required fields when CORREIOS_ENABLED is true.
    """
    enabled = getattr(settings, "CORREIOS_ENABLED", False)

    config = CorreiosConfig(
        enabled=enabled,
        usuario=(getattr(settings, "CORREIOS_USUARIO", "") or "").strip(),
        codigo_acesso=(getattr(settings, "CORREIOS_CODIGO_ACESSO", "") or "").strip(),
        cartao_postagem=(getattr(settings, "CORREIOS_CARTAO_POSTAGEM", "") or "").strip(),
        contrato=(getattr(settings, "CORREIOS_CONTRATO", "") or "").strip(),
        dr=(getattr(settings, "CORREIOS_DR", "") or "").strip(),
        cnpj=(getattr(settings, "CORREIOS_CNPJ", "") or "").strip(),
        cep_origem=(getattr(settings, "CORREIOS_CEP_ORIGEM", "") or "").strip(),
        pac_product_code=(getattr(settings, "CORREIOS_PAC_PRODUCT_CODE", "03298") or "").strip(),
        sedex_product_code=(getattr(settings, "CORREIOS_SEDEX_PRODUCT_CODE", "03220") or "").strip(),
        connect_timeout=float(getattr(settings, "CORREIOS_CONNECT_TIMEOUT_SECONDS", 5)),
        read_timeout=float(getattr(settings, "CORREIOS_READ_TIMEOUT_SECONDS", 15)),
        token_cache_margin_seconds=int(getattr(settings, "CORREIOS_TOKEN_CACHE_MARGIN_SECONDS", 300)),
        allow_estimate_fallback=bool(getattr(settings, "CORREIOS_ALLOW_ESTIMATE_FALLBACK", False)),
        default_length_cm=int(getattr(settings, "CORREIOS_DEFAULT_LENGTH_CM", 20)),
        default_width_cm=int(getattr(settings, "CORREIOS_DEFAULT_WIDTH_CM", 20)),
        default_height_cm=int(getattr(settings, "CORREIOS_DEFAULT_HEIGHT_CM", 20)),
    )

    if not enabled:
        return config

    if not config.usuario:
        raise FreightConfigurationError("CORREIOS_USUARIO nao configurado.")

    if not config.codigo_acesso:
        raise FreightConfigurationError("CORREIOS_CODIGO_ACESSO nao configurado.")

    if not config.cep_origem or not _is_valid_cep(config.cep_origem):
        raise FreightConfigurationError(_CEP_REQUIRED_MESSAGE)

    if not config.pac_product_code:
        raise FreightConfigurationError("CORREIOS_PAC_PRODUCT_CODE nao configurado.")

    if not config.sedex_product_code:
        raise FreightConfigurationError("CORREIOS_SEDEX_PRODUCT_CODE nao configurado.")

    if config.cnpj and len(config.cnpj) != 14:
        raise FreightConfigurationError("CORREIOS_CNPJ precisa ter 14 digitos.")

    if config.connect_timeout <= 0:
        raise FreightConfigurationError("CORREIOS_CONNECT_TIMEOUT_SECONDS deve ser positivo.")

    if config.read_timeout <= 0:
        raise FreightConfigurationError("CORREIOS_READ_TIMEOUT_SECONDS deve ser positivo.")

    for field_name, value in [
        ("CORREIOS_USUARIO", config.usuario),
        ("CORREIOS_CODIGO_ACESSO", config.codigo_acesso),
    ]:
        _reject_placeholder(value, field_name)

    return config


def _is_valid_cep(cep: str) -> bool:
    return len(cep) == 8 and cep.isdigit()


def _reject_placeholder(value: str, field_name: str) -> None:
    lower = value.lower()
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern in lower:
            raise FreightConfigurationError(
                f"{field_name} parece conter um placeholder. "
                "Configure a credencial real dos Correios."
            )


PACKAGE_PRESETS = [
    {
        "name": "Envelope",
        "weight_grams": 100,
        "length_cm": 20,
        "width_cm": 15,
        "height_cm": 2,
    },
    {
        "name": "Caixa P",
        "weight_grams": 500,
        "length_cm": 20,
        "width_cm": 20,
        "height_cm": 10,
    },
    {
        "name": "Caixa M",
        "weight_grams": 1000,
        "length_cm": 30,
        "width_cm": 25,
        "height_cm": 15,
    },
    {
        "name": "Caixa G",
        "weight_grams": 2000,
        "length_cm": 40,
        "width_cm": 30,
        "height_cm": 20,
    },
    {
        "name": "Personalizado",
        "weight_grams": 0,
        "length_cm": 0,
        "width_cm": 0,
        "height_cm": 0,
    },
]
