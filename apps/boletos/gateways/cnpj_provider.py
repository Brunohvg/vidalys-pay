"""BrasilAPI CNPJ gateway."""
import logging
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger("apps.boletos.cnpj")


class CnpjProviderError(Exception):
    """Base exception for safe provider failure mapping."""


class CnpjNotFoundError(CnpjProviderError):
    """The provider has no company for the requested CNPJ."""


class CnpjProviderTimeoutError(CnpjProviderError):
    """The provider did not respond within the configured timeout."""


class CnpjProviderUnavailableError(CnpjProviderError):
    """The provider failed or returned an unusable response."""


class BrasilApiCnpjGateway:
    """HTTP adapter that does not leak BrasilAPI payloads into the domain."""

    def __init__(self, client: httpx.Client | None = None):
        self.base_url = settings.CNPJ_LOOKUP_BASE_URL.rstrip("/")
        self._client = client
        self._timeout = httpx.Timeout(
            connect=settings.CNPJ_LOOKUP_CONNECT_TIMEOUT_SECONDS,
            read=settings.CNPJ_LOOKUP_READ_TIMEOUT_SECONDS,
            write=5,
            pool=5,
        )

    def lookup(self, cnpj: str) -> dict[str, Any]:
        url = f"{self.base_url}/{cnpj}"
        headers = {
            "Accept": "application/json",
            "User-Agent": settings.CNPJ_LOOKUP_USER_AGENT,
        }

        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, timeout=self._timeout)
            else:
                response = httpx.get(url, headers=headers, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            logger.warning("cnpj_lookup_timeout=true cnpj_prefix=%s", cnpj[:8])
            raise CnpjProviderTimeoutError from exc
        except httpx.RequestError as exc:
            logger.warning("cnpj_lookup_unavailable=true cnpj_prefix=%s", cnpj[:8])
            raise CnpjProviderUnavailableError from exc

        if response.status_code == 404:
            raise CnpjNotFoundError
        if response.status_code >= 500:
            logger.warning(
                "cnpj_lookup_provider_error=true status=%d cnpj_prefix=%s",
                response.status_code,
                cnpj[:8],
            )
            raise CnpjProviderUnavailableError
        if response.status_code >= 400:
            raise CnpjNotFoundError

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("cnpj_lookup_invalid_json=true cnpj_prefix=%s", cnpj[:8])
            raise CnpjProviderUnavailableError from exc

        if not isinstance(payload, dict):
            raise CnpjProviderUnavailableError
        return payload
