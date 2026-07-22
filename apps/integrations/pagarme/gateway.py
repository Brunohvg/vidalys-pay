"""Pagar.me HTTP gateway — V5 API integration.

Centralized client with proper auth header construction,
diagnostic logging, and no double-encoding.
"""
import logging
from typing import Any

import httpx
from django.conf import settings

from .credentials import (
    PagarMeConfigurationError,
    build_basic_auth_header,
    get_pagarme_api_key,
    normalize_pagarme_api_key,
)

logger = logging.getLogger("apps.integrations.pagarme")


class PagarmeError(Exception):
    """Pagar.me API error with status code and response data."""

    def __init__(self, status_code: int, error_data: dict):
        self.status_code = status_code
        self.error_data = error_data
        super().__init__(f"Pagar.me error {status_code}: {error_data}")


class PagarMeGateway:
    """HTTP gateway for Pagar.me V5 API.

    Handles credential normalization, Basic Auth header construction,
    and diagnostic logging for authentication failures.
    """

    BASE_URL = "https://api.pagar.me/core/v5"

    def __init__(self, api_key: str | None = None):
        self.api_key = normalize_pagarme_api_key(
            api_key or get_pagarme_api_key()
        )

        if not self.api_key:
            raise PagarMeConfigurationError(
                "Credencial da Pagar.me nao configurada."
            )

        configured_base = getattr(settings, "PAGARME_BASE_URL", "") or ""
        self.base_url = (configured_base or self.BASE_URL).rstrip("/")

        self._timeout = httpx.Timeout(
            connect=getattr(settings, "PAGARME_CONNECT_TIMEOUT_SECONDS", 5),
            read=getattr(settings, "PAGARME_READ_TIMEOUT_SECONDS", 20),
            write=20,
            pool=5,
        )

    @property
    def payment_links_url(self) -> str:
        return f"{self.base_url}/paymentlinks"

    def _get_headers(self) -> dict:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": build_basic_auth_header(self.api_key),
        }

    def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> dict[str, Any]:
        headers = self._get_headers()

        extra_headers = kwargs.pop("headers", {}) or {}

        if any(k.lower() == "authorization" for k in extra_headers):
            raise PagarMeConfigurationError(
                "O header Authorization nao pode ser sobrescrito."
            )

        headers.update(extra_headers)

        _log_request_diagnostics(method, url, headers)

        response = httpx.request(
            method,
            url,
            headers=headers,
            timeout=kwargs.pop("timeout", self._timeout),
            **kwargs,
        )

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
            logger.error(
                "Pagar.me HTTP %d: %s",
                response.status_code,
                error_data,
            )

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
            reference,
            amount_cents,
            installments,
        )

        data = self._request("POST", self.payment_links_url, json=payload)

        logger.info(
            "Link criado: id=%s status=%s",
            data.get("id"),
            data.get("status"),
        )
        return data

    def get_payment_link(self, link_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/paymentlinks/{link_id}"
        return self._request("GET", url)

    def cancel_payment_link(self, link_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/paymentlinks/{link_id}"
        return self._request(
            "PATCH", url, json={"is_building": True}
        )


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
    request_headers = getattr(response, "request", None)
    if request_headers is not None:
        request_headers = getattr(request_headers, "headers", {})
        auth_header = request_headers.get("authorization", "")
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


def get_gateway() -> PagarMeGateway:
    return PagarMeGateway()
