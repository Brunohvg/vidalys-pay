"""Pagar.me HTTP client — V5 API integration.

Authentication: Basic Auth with Secret Key as username, empty password.
Uses the credential normalizer to accept multiple input formats safely.
"""
import logging
from typing import Any

import httpx
from django.conf import settings

from .credentials import (
    PagarMeConfigurationError,
    build_basic_auth_header,
    get_pagarme_api_key,
)

logger = logging.getLogger("apps.integrations.pagarme")

BOLETO_LATE_PAYMENT_INSTRUCTIONS = (
    "Após o vencimento: multa de 2% e juros de mora de 1% ao mês."
)
BOLETO_INTEREST_PERCENT_MONTHLY = 1
BOLETO_FINE_PERCENT = 2
BOLETO_LATE_FEE_START_DAYS = 1


class PagarmeError(Exception):
    def __init__(self, status_code: int, error_data: dict):
        self.status_code = status_code
        self.error_data = error_data
        super().__init__(f"Pagar.me error {status_code}: {error_data}")


class PagarmeClient:
    """HTTP client for Pagar.me V5 API."""

    def __init__(self):
        self.base_url = settings.PAGARME_BASE_URL.rstrip("/")
        self.api_key = get_pagarme_api_key()

        if not self.api_key:
            raise PagarMeConfigurationError(
                "Credencial da Pagar.me nao configurada."
            )

        self._timeout = httpx.Timeout(
            connect=getattr(settings, "PAGARME_CONNECT_TIMEOUT_SECONDS", 5),
            read=getattr(settings, "PAGARME_READ_TIMEOUT_SECONDS", 20),
            write=20,
            pool=5,
        )

    def _headers(self) -> dict:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": build_basic_auth_header(self.api_key),
        }

    def _post(
        self,
        path: str,
        json: dict,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self._headers()
        extra_headers = extra_headers or {}
        if any(key.lower() == "authorization" for key in extra_headers):
            raise ValueError("O header Authorization não pode ser sobrescrito.")
        headers.update(extra_headers)
        _log_request_diagnostics("POST", url, headers)
        response = httpx.post(url, json=json, headers=headers, timeout=self._timeout)
        return self._handle_response(response)

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self._headers()
        _log_request_diagnostics("GET", url, headers)
        response = httpx.get(url, headers=headers, timeout=self._timeout)
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
            _log_401_diagnostics(response)
        elif response.status_code == 403:
            logger.error(
                "Pagar.me 403: acesso nao autorizado. "
                "Verifique permissoes da conta. "
                "correlation_id=%s",
                response.headers.get("x-request-id", ""),
            )
        elif response.status_code == 429:
            logger.error(
                "Pagar.me 429: limite de chamadas excedido. "
                "correlation_id=%s",
                response.headers.get("x-request-id", ""),
            )
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

    def create_boleto_order(
        self,
        *,
        code: str,
        amount_cents: int,
        description: str,
        due_date: str,
        customer: dict[str, Any],
        metadata: dict[str, str],
        idempotency_key: str,
        instructions: str = BOLETO_LATE_PAYMENT_INSTRUCTIONS,
    ) -> dict[str, Any]:
        """Create a Pagar.me V5 order paid by boleto."""
        boleto: dict[str, Any] = {
            "due_at": f"{due_date}T23:59:59Z",
            "interest": {
                "days": BOLETO_LATE_FEE_START_DAYS,
                "type": "percentage",
                "amount": BOLETO_INTEREST_PERCENT_MONTHLY,
            },
            "fine": {
                "days": BOLETO_LATE_FEE_START_DAYS,
                "type": "percentage",
                "amount": BOLETO_FINE_PERCENT,
            },
        }
        if instructions:
            boleto["instructions"] = instructions[:255]

        payload = {
            "code": code,
            "customer": customer,
            "items": [
                {
                    "amount": amount_cents,
                    "description": description[:255],
                    "quantity": 1,
                    "code": code,
                }
            ],
            "payments": [
                {
                    "payment_method": "boleto",
                    "boleto": boleto,
                }
            ],
            "metadata": metadata,
        }

        logger.info(
            "Criando boleto Pagar.me: code=%s amount=%d",
            code,
            amount_cents,
        )
        return self._post(
            "orders",
            payload,
            extra_headers={"Idempotency-Key": idempotency_key},
        )


def get_client() -> PagarmeClient:
    return PagarmeClient()


def _log_request_diagnostics(method: str, url: str, headers: dict) -> None:
    auth_present = "Authorization" in headers
    auth_value = headers.get("Authorization", "")
    is_basic = auth_value.startswith("Basic ") if auth_present else False

    logger.info(
        "Chamada Pagar.me: method=%s endpoint=%s "
        "auth_present=%s auth_scheme=%s",
        method,
        _safe_endpoint(url),
        auth_present,
        "Basic" if is_basic else ("other" if auth_present else "absent"),
    )


def _log_401_diagnostics(response: httpx.Response) -> None:
    auth_sent = False
    is_basic = False
    req = getattr(response, "request", None)
    if req is not None:
        req_headers = getattr(req, "headers", {}) or {}
        auth_header = req_headers.get("authorization", "")
        auth_sent = bool(auth_header)
        is_basic = auth_header.startswith("Basic ")

    logger.error(
        "Pagar.me 401 — diagnostico: "
        "auth_header_enviado=%s "
        "auth_scheme_basic=%s "
        "endpoint=%s "
        "correlation_id=%s "
        "response_body=%s",
        auth_sent,
        is_basic,
        _safe_endpoint(str(response.url)),
        response.headers.get("x-request-id", ""),
        (response.text or "")[:200],
    )


def _safe_endpoint(url: str) -> str:
    if "/paymentlinks" in url or "/paymentlinks/" in url:
        return "/paymentlinks"
    parts = url.split("/")
    for part in parts:
        if part and not part.startswith("http"):
            return f"/{part}"
    return url
