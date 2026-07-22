"""Pagar.me credential normalization.

Handles multiple input formats and produces a canonical Basic Auth header.
All valid inputs must produce identical output for the same Secret Key.

Accepted formats:
  A) Raw Secret Key:         sk_test_abc123...
  B) Pre-encoded Base64:     c2tfdGVzdF9hYmMxMjM6
  C) Full Basic header:      Basic c2tfdGVzdF9hYmMxMjM6
"""
import base64
import binascii
import re
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured

_SECRET_KEY_RE = re.compile(r"^sk_(live_|test_)?[A-Za-z0-9]+$")
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]+=*$")


class CredentialError(ImproperlyConfigured):
    """Credential parsing or validation error."""


@dataclass(frozen=True)
class NormalizedCredential:
    """Canonical representation of a Pagar.me credential."""
    secret_key: str
    authorization_header: str
    source_format: str   # "raw_secret_key" | "base64_credentials" | "basic_header"
    environment: str     # "production" | "test"


def normalize_credential(value: str) -> NormalizedCredential:
    """Normalize a Pagar.me credential from any supported format.

    Raises CredentialError if the input is invalid.
    """
    candidate = (value or "").strip()

    if not candidate:
        raise CredentialError("Credencial da Pagar.me não configurada.")

    if "\n" in candidate or "\r" in candidate:
        raise CredentialError("Credencial contém quebra de linha.")

    # Format C: "Basic ..." header
    if candidate.lower().startswith("basic "):
        encoded = candidate[6:].strip()
        if not encoded:
            raise CredentialError("Cabeçalho Basic sem valor codificado.")
        secret_key = _decode_credentials(encoded)
        return _build_result(secret_key, "basic_header")

    # Format A: Raw Secret Key
    if _SECRET_KEY_RE.match(candidate):
        return _build_result(candidate, "raw_secret_key")

    # Format B: Pre-encoded Base64
    if _BASE64_RE.match(candidate) and len(candidate) >= 8:
        secret_key = _decode_credentials(candidate)
        return _build_result(secret_key, "base64_credentials")

    raise CredentialError(
        "Formato da credencial Pagar.me não reconhecido. "
        "Use a Secret Key original (sk_...), Base64 de 'sk_...:' , "
        "ou cabeçalho 'Basic ...'."
    )


def _decode_credentials(encoded: str) -> str:
    """Decode a base64-encoded Basic Auth credentials string.

    Expected format after decoding: "secret_key:"
    """
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as e:
        raise CredentialError(f"Base64 inválido: {e}") from e

    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise CredentialError("Conteúdo decodificado não é UTF-8 válido.") from e

    if ":" not in decoded:
        raise CredentialError(
            "Credencial decodificada não contém separador ':'. "
            "Formato esperado: 'secret_key:'."
        )

    username, password = decoded.split(":", 1)

    if not username:
        raise CredentialError("Usuário Basic Auth vazio.")

    if password != "":
        raise CredentialError(
            "A senha do Basic Auth da Pagar.me deve estar vazia. "
            "Recebido: '***'."
        )

    if not _SECRET_KEY_RE.match(username):
        raise CredentialError(
            "O usuário decodificado não parece ser uma Secret Key Pagar.me. "
            "Esperado prefixo sk_ ou sk_test_."
        )

    return username


def _build_result(secret_key: str, source_format: str) -> NormalizedCredential:
    """Build canonical representation."""
    env = _detect_environment(secret_key)
    basic_bytes = f"{secret_key}:".encode("utf-8")
    encoded = base64.b64encode(basic_bytes).decode("ascii")
    return NormalizedCredential(
        secret_key=secret_key,
        authorization_header=f"Basic {encoded}",
        source_format=source_format,
        environment=env,
    )


def _detect_environment(secret_key: str) -> str:
    if secret_key.startswith("sk_test_"):
        return "test"
    return "production"


def get_credential() -> NormalizedCredential:
    """Get the normalized Pagar.me credential from settings.

    Precedence: PAGARME_CREDENTIAL > PAGARME_SECRET_KEY (deprecated).
    """
    from django.conf import settings

    credential = getattr(settings, "PAGARME_CREDENTIAL", "") or ""
    legacy_key = getattr(settings, "PAGARME_SECRET_KEY", "") or ""

    if credential:
        return normalize_credential(credential)

    if legacy_key:
        import logging
        logging.getLogger("apps.integrations.pagarme").warning(
            "PAGARME_SECRET_KEY está em uso. Migre para PAGARME_CREDENTIAL que "
            "aceita Secret Key original, Base64 ou cabeçalho Basic."
        )
        return normalize_credential(legacy_key)

    raise CredentialError("Nenhuma credencial Pagar.me configurada.")
