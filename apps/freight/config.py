"""Centralized Correios configuration — simplified.

Only 6 environment variables are required:
  CORREIOS_USUARIO
  CORREIOS_CODIGO_ACESSO
  CORREIOS_CARTAO_POSTAGEM
  CORREIOS_CONTRATO
  CORREIOS_CNPJ
  CORREIOS_CEP_ORIGEM

All other behaviours (timeouts, product codes, limits) are internal constants.
"""
import logging
import os
import re
from dataclasses import dataclass

from django.conf import settings

from .exceptions import FreightConfigurationError

logger = logging.getLogger("apps.freight")

_CEP_RE = re.compile(r"^\d{8}$")
_CNPJ_RE = re.compile(r"^\d{14}$")
_PLACEHOLDER_PATTERNS = ("configure-no", "troque", "seu-", "gere-um")

# ── internal constants (never from env) ──────────────────────────────────────

REQUEST_TIMEOUT_SECONDS = 10
TOKEN_CACHE_MARGIN_SECONDS = 300
DEFAULT_FALLBACK_LENGTH_CM = "20"
DEFAULT_FALLBACK_WIDTH_CM = "20"
DEFAULT_FALLBACK_HEIGHT_CM = "20"

TOKEN_URL = "https://api.correios.com.br/token/v1/autentica"
TOKEN_URL_CARTAO = "https://api.correios.com.br/token/v1/autentica/cartaopostagem"
MEU_CONTRATO_URL = "https://api.correios.com.br/meucontrato/v1"
PRICE_URL = "https://api.correios.com.br/preco/v1/nacional"
DEADLINE_URL = "https://api.correios.com.br/prazo/v1/nacional"

DEFAULT_PRODUCTS = ["03298", "03220"]


# ── additional delivery days ─────────────────────────────────────────────────

def get_additional_delivery_days() -> int:
    """CORREIOS_DIAS_ADICIONAIS — extra days added to the provider deadline.

    Default 0.  Invalid/negative values are clamped to 0 with a warning.
    """
    from django.conf import settings

    raw = getattr(settings, "CORREIOS_DIAS_ADICIONAIS", "0")
    try:
        days = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "correios_dias_adicionais_invalido=true raw=%s", repr(raw),
        )
        return 0

    if days < 0:
        logger.warning(
            "correios_dias_adicionais_negativo=true raw=%s clamped=0", repr(raw),
        )
        return 0

    return days

PRODUCT_LABELS = {
    "03298": "PAC",
    "03220": "SEDEX",
}


# ── dataclass ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CorreiosConfig:
    usuario: str
    codigo_acesso: str
    cartao_postagem: str
    contrato: str
    cnpj: str
    cep_origem: str


# ── factory ──────────────────────────────────────────────────────────────────

def get_correios_config() -> CorreiosConfig:
    """Build validated CorreiosConfig from Django settings.

    Only 6 env vars are consumed. Old variables (CORREIOS_DR,
    CORREIOS_ENABLED, CORREIOS_PAC_PRODUCT_CODE, etc.) are ignored
    with a single warning.
    """
    _warn_legacy_vars()

    config = CorreiosConfig(
        usuario=_clean_str(getattr(settings, "CORREIOS_USUARIO", "")),
        codigo_acesso=_clean_str(getattr(settings, "CORREIOS_CODIGO_ACESSO", "")),
        cartao_postagem=_digits_only(getattr(settings, "CORREIOS_CARTAO_POSTAGEM", "")),
        contrato=_digits_only(getattr(settings, "CORREIOS_CONTRATO", "")),
        cnpj=_digits_only(getattr(settings, "CORREIOS_CNPJ", "")),
        cep_origem=_digits_only(getattr(settings, "CORREIOS_CEP_ORIGEM", "")),
    )

    return config


def is_correios_configured(config: CorreiosConfig) -> bool:
    """True when the three mandatory fields are present."""
    return bool(config.usuario and config.codigo_acesso and config.cep_origem)


# ── validators ───────────────────────────────────────────────────────────────

def validate_correios_config(config: CorreiosConfig) -> None:
    """Raise FreightConfigurationError if config is incomplete or invalid."""
    if not config.usuario:
        raise FreightConfigurationError("CORREIOS_USUARIO nao configurado.")

    if not config.codigo_acesso:
        raise FreightConfigurationError("CORREIOS_CODIGO_ACESSO nao configurado.")

    if not config.cep_origem or not _CEP_RE.match(config.cep_origem):
        raise FreightConfigurationError(
            "CORREIOS_CEP_ORIGEM invalido. Precisa ter exatamente 8 digitos."
        )

    if config.cnpj and not _CNPJ_RE.match(config.cnpj):
        raise FreightConfigurationError(
            "CORREIOS_CNPJ precisa ter 14 digitos."
        )

    for name, value in [
        ("CORREIOS_USUARIO", config.usuario),
        ("CORREIOS_CODIGO_ACESSO", config.codigo_acesso),
    ]:
        _reject_placeholder(value, name)


# ── helpers ──────────────────────────────────────────────────────────────────

def _clean_str(value: str) -> str:
    return (value or "").strip()


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _reject_placeholder(value: str, name: str) -> None:
    lower = value.lower()
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern in lower:
            raise FreightConfigurationError(
                f"{name} parece conter um placeholder. "
                "Configure a credencial real dos Correios."
            )


_LEGACY_VARS = [
    "CORREIOS_ENABLED",
    "CORREIOS_DR",
    "CORREIOS_PAC_PRODUCT_CODE",
    "CORREIOS_SEDEX_PRODUCT_CODE",
    "CORREIOS_CONNECT_TIMEOUT_SECONDS",
    "CORREIOS_READ_TIMEOUT_SECONDS",
    "CORREIOS_TOKEN_CACHE_MARGIN_SECONDS",
    "CORREIOS_ALLOW_ESTIMATE_FALLBACK",
    "CORREIOS_DEFAULT_LENGTH_CM",
    "CORREIOS_DEFAULT_WIDTH_CM",
    "CORREIOS_DEFAULT_HEIGHT_CM",
]

_legacy_warned = False


def _warn_legacy_vars() -> None:
    global _legacy_warned
    if _legacy_warned:
        return
    found = [v for v in _LEGACY_VARS if os.environ.get(v)]
    if found:
        logger.warning(
            "Variáveis antigas dos Correios detectadas e ignoradas: %s",
            ", ".join(sorted(found)),
        )
    _legacy_warned = True


# ── package presets (UI) ─────────────────────────────────────────────────────

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
