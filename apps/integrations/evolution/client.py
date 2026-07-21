"""Evolution API HTTP client — V2 integration.

Endpoint: POST {EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}
Auth: header apikey
"""
import logging
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger("apps.integrations.evolution")

DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=3.0)


class EvolutionError(Exception):
    """Evolution API error."""

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Evolution error {status_code}: {detail}")


class EvolutionClient:
    """HTTP client for Evolution API v2 — sendText."""

    def __init__(self):
        self.base_url = settings.EVOLUTION_API_URL.rstrip("/")
        self.api_key = settings.EVOLUTION_API_KEY
        self.instance = settings.EVOLUTION_INSTANCE

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "apikey": self.api_key,
        }

    def send_text(self, *, phone: str, text: str, link_preview: bool = True) -> dict[str, Any]:
        """Send plain text message via WhatsApp.

        Args:
            phone: E.164 phone number (e.g., "5531999999999")
            text: Message content
            link_preview: Enable URL preview in message

        Returns:
            API response with message ID and status.
        """
        url = f"{self.base_url}/message/sendText/{self.instance}"

        payload = {
            "number": phone,
            "text": text,
            "linkPreview": link_preview,
        }

        logger.info("Enviando WhatsApp para %s (%d chars)", phone, len(text))

        try:
            response = httpx.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=DEFAULT_TIMEOUT,
            )

            if response.status_code >= 400:
                detail = response.text[:500] if response.text else ""
                logger.error("Evolution erro %d: %s", response.status_code, detail)
                raise EvolutionError(response.status_code, detail)

            data = response.json()
            logger.info("WhatsApp enviado: %s", data.get("key", {}).get("id", "unknown"))
            return data

        except httpx.TimeoutException as err:
            logger.error("Evolution timeout ao enviar para %s", phone)
            raise EvolutionError(408, "Timeout") from err


def get_client() -> EvolutionClient:
    """Get an Evolution client instance."""
    return EvolutionClient()
