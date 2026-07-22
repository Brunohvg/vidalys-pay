"""Pagar.me HTTP client — V5 API integration.

Authentication: Basic Auth with Secret Key as username, empty password.
Uses the credential normalizer to accept multiple input formats safely.
"""
import logging
from typing import Any

import httpx
from django.conf import settings

from .credentials import get_credential

logger = logging.getLogger("apps.integrations.pagarme")


class PagarmeError(Exception):
    def __init__(self, status_code: int, error_data: dict):
        self.status_code = status_code
        self.error_data = error_data
        super().__init__(f"Pagar.me error {status_code}: {error_data}")


class PagarmeClient:
    """HTTP client for Pagar.me V5 API."""

    def __init__(self):
        self.base_url = settings.PAGARME_BASE_URL.rstrip("/")
        self._credential = get_credential()
        self._timeout = httpx.Timeout(
            connect=getattr(settings, "PAGARME_CONNECT_TIMEOUT_SECONDS", 5),
            read=getattr(settings, "PAGARME_READ_TIMEOUT_SECONDS", 20),
            write=20,
            pool=5,
        )

    def _headers(self) -> dict:
        return {
            "Authorization": self._credential.authorization_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post(self, path: str, json: dict) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = httpx.post(url, json=json, headers=self._headers(), timeout=self._timeout)
        return self._handle_response(response)

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = httpx.get(url, headers=self._headers(), timeout=self._timeout)
        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code < 400:
            return response.json()

        error_data = {}
        try:
            error_data = response.json() if response.text else {}
        except Exception:
            error_data = {"raw": response.text[:200]}

        if response.status_code == 401:
            logger.error("Pagar.me 401: autenticação recusada")
        elif response.status_code == 403:
            logger.error("Pagar.me 403: acesso não autorizado (conta/permissão)")
        elif response.status_code == 429:
            logger.error("Pagar.me 429: rate limit")
        else:
            logger.error("Pagar.me HTTP %d: %s", response.status_code, error_data)

        raise PagarmeError(response.status_code, error_data)

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

        if expires_in_minutes is not None:
            payload["expires_in"] = expires_in_minutes

        if metadata:
            payload["metadata"] = metadata

        logger.info(
            "Criando link Pagar.me: ref=%s amount=%d installments=%d",
            reference, amount_cents, installments,
        )

        data = self._post("paymentlinks", payload)

        logger.info(
            "Link criado: id=%s status=%s",
            data.get("id"), data.get("status"),
        )
        return data

    def get_payment_link(self, link_id: str) -> dict[str, Any]:
        return self._get(f"paymentlinks/{link_id}")

    def cancel_payment_link(self, link_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/paymentlinks/{link_id}"
        response = httpx.patch(
            url,
            json={"is_building": True},
            headers=self._headers(),
            timeout=self._timeout,
        )
        return self._handle_response(response)


def get_client() -> PagarmeClient:
    return PagarmeClient()
