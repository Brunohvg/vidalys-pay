"""Pagar.me HTTP client — V5 API integration.

Authentication: Basic Auth with SecretKey as username, empty password.
- Sandbox: sk_test_* → https://sdx-api.pagar.me/core/v5
- Production: sk_* → https://api.pagar.me/core/v5
"""
import base64
import logging
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger("apps.integrations.pagarme")

# Timeouts: connection 3s, read 10s
DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=3.0)


class PagarmeError(Exception):
    """Base exception for Pagar.me errors."""

    def __init__(self, status_code: int, error_data: dict):
        self.status_code = status_code
        self.error_data = error_data
        super().__init__(f"Pagar.me error {status_code}: {error_data}")


class PagarmeClient:
    """HTTP client for Pagar.me V5 API."""

    def __init__(self):
        self.base_url = settings.PAGARME_BASE_URL.rstrip("/")
        self.secret_key = settings.PAGARME_SECRET_KEY
        self._auth_header = self._build_auth()

    def _build_auth(self) -> str:
        """Build Basic Auth header: base64(secret_key:).

        Aceita tanto a chave raw (sk_xxx) quanto já convertida em base64.
        """
        key = self.secret_key.strip()

        # Se já parece ser base64 (contém apenas chars válidos de base64 e tem tamanho par)
        # e NÃO começa com sk_, assume que já está convertido
        if not key.startswith("sk_") and self._is_likely_base64(key):
            return f"Basic {key}"

        # Senão, converte: base64(secret_key:)
        credentials = f"{key}:"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    @staticmethod
    def _is_likely_base64(value: str) -> bool:
        """Check if a string looks like it's already base64 encoded."""
        import re
        # Base64 chars: A-Z, a-z, 0-9, +, /, =
        # Typical base64 length is multiple of 4 (with padding)
        if not value:
            return False
        pattern = re.compile(r'^[A-Za-z0-9+/]+=*$')
        return bool(pattern.match(value)) and len(value) >= 8

    def _headers(self) -> dict:
        return {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def create_payment_link(
        self,
        *,
        name: str,
        reference: str,
        amount_cents: int,
        installments: int,
        max_paid_sessions: int = 1,
        expires_in_minutes: int | None = None,
        customer_name: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Create a payment link (checkout) for one-time order.

        Returns the full API response including id, url, status.
        """
        # Build installments array: each installment has number and total
        installments_list = [
            {"number": i, "total": amount_cents}
            for i in range(1, installments + 1)
        ]

        payload: dict[str, Any] = {
            "type": "order",
            "is_building": False,
            "name": name[:64],
            "order_code": reference,
            "max_paid_sessions": max_paid_sessions,
            "payment_settings": {
                "accepted_payment_methods": ["credit_card"],
                "credit_card_settings": {
                    "operation_type": "auth_and_capture",
                    "installments": installments_list,
                },
            },
            "cart_settings": {
                "items": [
                    {
                        "amount": amount_cents,
                        "name": f"Pedido {reference}",
                        "default_quantity": 1,
                    }
                ],
            },
        }

        # Optional fields
        if expires_in_minutes is not None:
            payload["expires_in"] = expires_in_minutes

        if metadata:
            payload["metadata"] = metadata

        logger.info(
            "Criando link Pagar.me: ref=%s amount=%d installments=%d",
            reference,
            amount_cents,
            installments,
        )

        response = httpx.post(
            f"{self.base_url}/paymentlinks",
            json=payload,
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )

        if response.status_code >= 400:
            error_data = response.json() if response.text else {}
            logger.error(
                "Pagar.me erro %d: %s",
                response.status_code,
                error_data,
            )
            raise PagarmeError(response.status_code, error_data)

        data = response.json()
        logger.info(
            "Link criado: id=%s status=%s url=%s",
            data.get("id"),
            data.get("status"),
            data.get("url", "")[:50],
        )
        return data

    def get_payment_link(self, link_id: str) -> dict[str, Any]:
        """Get payment link by ID."""
        response = httpx.get(
            f"{self.base_url}/paymentlinks/{link_id}",
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )

        if response.status_code >= 400:
            error_data = response.json() if response.text else {}
            raise PagarmeError(response.status_code, error_data)

        return response.json()

    def cancel_payment_link(self, link_id: str) -> dict[str, Any]:
        """Cancel a payment link."""
        response = httpx.patch(
            f"{self.base_url}/paymentlinks/{link_id}",
            json={"is_building": True},
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )

        if response.status_code >= 400:
            error_data = response.json() if response.text else {}
            raise PagarmeError(response.status_code, error_data)

        return response.json()


def get_client() -> PagarmeClient:
    """Get a Pagar.me client instance."""
    return PagarmeClient()
