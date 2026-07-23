"""Pagar.me credential normalization.

Accepts multiple input formats and always returns the raw Secret Key.
All valid inputs must produce identical output for the same Secret Key.

Accepted formats:
  A) Raw Secret Key:         sk_test_abc123...
  B) Pre-encoded Base64:     c2tfdGVzdF9hYmMxMjM6  (of "sk_...:")
  C) Full Basic header:      Basic c2tfdGVzdF9hYmMxMjM6
"""
import base64
import binascii
import logging
import re

from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger("apps.integrations.pagarme")

_SECRET_KEY_RE = re.compile(r"^sk_(live_|test_)?[A-Za-z0-9]+$")
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]+=*$")


class PagarMeConfigurationError(ImproperlyConfigured):
    """Credential parsing or validation error."""


def normalize_pagarme_api_key(value: str) -> str:
    """Normalize a Pagar.me credential from any supported format.

    Always returns the raw Secret Key (sk_...).
    Never returns Base64 or Basic header as the internal key.

    Raises PagarMeConfigurationError if the input is invalid.
    """
    candidate = (value or "").strip()

    if not candidate:
        raise PagarMeConfigurationError(
            "Credencial da Pagar.me nao configurada."
        )

    if "\n" in candidate or "\r" in candidate:
        raise PagarMeConfigurationError(
            "A credencial Pagar.me contem quebra de linha."
        )

    # Format C: "Basic ..." header
    if candidate.lower().startswith("basic "):
        candidate = candidate[6:].strip()
        if not candidate:
            raise PagarMeConfigurationError(
                "Cabecalho Basic sem valor codificado."
            )

    # Format A: Raw Secret Key — check before Base64
    if _SECRET_KEY_RE.match(candidate):
        return candidate

    # Format B: Pre-encoded Base64
    if _BASE64_RE.match(candidate) and len(candidate) >= 8:
        try:
            decoded_bytes = base64.b64decode(candidate, validate=True)
            decoded = decoded_bytes.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise PagarMeConfigurationError(
                "A credencial Pagar.me nao esta em um formato reconhecido."
            ) from exc

        if decoded.endswith(":"):
            decoded = decoded[:-1]

        if not decoded.startswith("sk_"):
            raise PagarMeConfigurationError(
                "A credencial decodificada nao representa uma Secret Key."
            )

        if ":" in decoded:
            raise PagarMeConfigurationError(
                "A credencial decodificada contem senha preenchida. "
                "A Pagar.me requer senha vazia."
            )

        return decoded

    raise PagarMeConfigurationError(
        "Formato da credencial Pagar.me nao reconhecido. "
        "Use a Secret Key original (sk_...), Base64 de 'sk_...:', "
        "ou cabecalho 'Basic ...'."
    )


def build_basic_auth_header(secret_key: str) -> str:
    """Build the Basic Auth header from a raw Secret Key."""
    encoded = base64.b64encode(
        f"{secret_key}:".encode()
    ).decode("ascii")
    return f"Basic {encoded}"


def get_pagarme_api_key() -> str:
    """Get the normalized Pagar.me API key from settings.

    Precedence: PAGARME_CREDENTIAL > PAGARME_SECRET_KEY (deprecated).

    Returns the raw Secret Key (sk_...).
    """
    from django.conf import settings

    credential = getattr(settings, "PAGARME_CREDENTIAL", "") or ""
    legacy_key = getattr(settings, "PAGARME_SECRET_KEY", "") or ""

    if credential:
        input_format = _detect_input_format(credential)
        try:
            api_key = normalize_pagarme_api_key(credential)
        except PagarMeConfigurationError:
            logger.exception(
                "Falha ao normalizar PAGARME_CREDENTIAL. "
                "input_format=%s",
                input_format,
            )
            raise

        logger.info(
            "Credencial Pagar.me carregada de PAGARME_CREDENTIAL. "
            "input_format=%s env=%s",
            input_format,
            "production" if not api_key.startswith("sk_test_") else "test",
        )
        return api_key

    if legacy_key:
        input_format = _detect_input_format(legacy_key)
        try:
            api_key = normalize_pagarme_api_key(legacy_key)
        except PagarMeConfigurationError:
            logger.exception(
                "Falha ao normalizar PAGARME_SECRET_KEY. "
                "input_format=%s",
                input_format,
            )
            raise

        logger.warning(
            "PAGARME_SECRET_KEY esta em uso (obsoleto). "
            "Migre para PAGARME_CREDENTIAL. "
            "input_format=%s env=%s",
            input_format,
            "production" if not api_key.startswith("sk_test_") else "test",
        )
        return api_key

    raise PagarMeConfigurationError(
        "Nenhuma credencial Pagar.me configurada. "
        "Defina PAGARME_CREDENTIAL no ambiente."
    )


def _detect_input_format(value: str) -> str:
    """Detect the input format of a credential value (for logging only)."""
    candidate = (value or "").strip()
    if not candidate:
        return "empty"
    if candidate.lower().startswith("basic "):
        return "basic_header"
    if _SECRET_KEY_RE.match(candidate):
        return "raw_secret_key"
    if _BASE64_RE.match(candidate):
        return "base64_credentials"
    return "unknown"
