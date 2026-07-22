"""Correios CWS (Web Services) client.

Authentication: obtains and caches a Bearer token.
Pricing/Deadline: queries PAC and SEDEX.
"""
import logging
import time
from typing import Any

import httpx
from django.core.cache import cache

from .config import get_correios_config
from .dataclasses import CorreiosToken, FreightOption, PackageData
from .exceptions import (
    FreightAuthenticationError,
    FreightProviderUnavailable,
)

logger = logging.getLogger("apps.freight")

TOKEN_CACHE_KEY = "correios:cws:token"
CORREIOS_API_BASE = "https://api.correios.com.br"


class CorreiosAuthClient:
    def __init__(self):
        self._config = get_correios_config()

    @property
    def _token_url(self) -> str:
        if self._config.cartao_postagem:
            return f"{CORREIOS_API_BASE}/token/v1/autentica/cartaopostagem"
        return f"{CORREIOS_API_BASE}/token/v1/autentica"

    @property
    def _auth_payload(self) -> dict:
        payload: dict[str, str] = {
            "numero": self._config.usuario,
        }
        if self._config.cartao_postagem:
            payload["codigoAcesso"] = self._config.codigo_acesso
            payload["cartaoPostagem"] = self._config.cartao_postagem
        else:
            payload["codigoAcesso"] = self._config.codigo_acesso
        return payload

    def get_token(self) -> str:
        cached = cache.get(TOKEN_CACHE_KEY)
        if cached and isinstance(cached, dict) and cached.get("access_token"):
            return cached["access_token"]

        token_data = self._authenticate()
        self._cache_token(token_data)
        return token_data.access_token

    def invalidate_token(self) -> None:
        cache.delete(TOKEN_CACHE_KEY)

    def _authenticate(self) -> CorreiosToken:
        try:
            response = httpx.post(
                self._token_url,
                json=self._auth_payload,
                headers={"Accept": "application/json"},
                timeout=httpx.Timeout(
                    connect=self._config.connect_timeout,
                    read=self._config.read_timeout,
                ),
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise FreightProviderUnavailable(
                "Os Correios demoraram para responder. Tente novamente."
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise FreightAuthenticationError(
                    "Nao foi possivel autenticar nos Correios."
                ) from exc
            raise FreightProviderUnavailable(
                "Os Correios estao indisponiveis. Tente novamente."
            ) from exc
        except httpx.RequestError as exc:
            raise FreightProviderUnavailable(
                "Nao foi possivel conectar aos Correios."
            ) from exc

        token = data.get("token") or data.get("access_token") or ""
        expires_in = data.get("expiraEm") or data.get("expires_in") or 3600

        if not token:
            raise FreightAuthenticationError(
                "Token nao encontrado na resposta dos Correios."
            )

        return CorreiosToken(
            access_token=token,
            expires_in=int(expires_in),
            token_type=data.get("tipo", "Bearer"),
        )

    def _cache_token(self, token_data: CorreiosToken) -> None:
        ttl = max(1, token_data.expires_in - self._config.token_cache_margin_seconds)
        cache.set(
            TOKEN_CACHE_KEY,
            {"access_token": token_data.access_token},
            timeout=ttl,
        )


class CorreiosFreightClient:
    SERVICE_NAMES = {
        "03298": "PAC",
        "03220": "SEDEX",
    }

    def __init__(self):
        self._config = get_correios_config()
        self._auth = CorreiosAuthClient()

    def calculate(self, package: PackageData) -> list[FreightOption]:
        services = [
            self._config.pac_product_code,
            self._config.sedex_product_code,
        ]

        token = self._auth.get_token()
        options: list[FreightOption] = []

        for service_code in services:
            option = self._calculate_for_service(
                token=token,
                service_code=service_code,
                package=package,
            )
            options.append(option)

        return options

    def _calculate_for_service(
        self,
        token: str,
        service_code: str,
        package: PackageData,
    ) -> FreightOption:
        service_name = self.SERVICE_NAMES.get(service_code, service_code)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        try:
            price = self._get_price(headers, service_code, package)
        except FreightProviderUnavailable:
            return FreightOption(
                provider="correios",
                service_code=service_code,
                service_name=service_name,
                price_cents=0,
                delivery_days=None,
                official=False,
                error="Preco indisponivel",
            )
        except FreightAuthenticationError:
            self._auth.invalidate_token()
            token = self._auth.get_token()
            headers["Authorization"] = f"Bearer {token}"
            try:
                price = self._get_price(headers, service_code, package)
            except (FreightProviderUnavailable, FreightAuthenticationError):
                return FreightOption(
                    provider="correios",
                    service_code=service_code,
                    service_name=service_name,
                    price_cents=0,
                    delivery_days=None,
                    official=False,
                    error="Preco indisponivel",
                )

        try:
            deadline = self._get_deadline(headers, service_code, package)
        except (FreightProviderUnavailable, FreightAuthenticationError):
            deadline = None

        return FreightOption(
            provider="correios",
            service_code=service_code,
            service_name=service_name,
            price_cents=price,
            delivery_days=deadline,
            official=True,
        )

    def _get_price(
        self,
        headers: dict,
        service_code: str,
        package: PackageData,
    ) -> int:
        url = (
            f"{CORREIOS_API_BASE}/preco/v1/nacional/{service_code}"
            f"?cepOrigem={self._config.cep_origem}"
            f"&cepDestino={package.destination_zip_code}"
            f"&psObjeto={package.weight_grams}"
            f"&tpObjeto=2"
            f"&comprimento={package.length_cm}"
            f"&largura={package.width_cm}"
            f"&altura={package.height_cm}"
            f"&servicosAdicionais="
        )

        if package.declared_value_cents > 0:
            url += f"&vlDeclarado={package.declared_value_cents / 100:.2f}"

        try:
            response = httpx.get(
                url,
                headers=headers,
                timeout=httpx.Timeout(
                    connect=self._config.connect_timeout,
                    read=self._config.read_timeout,
                ),
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise FreightProviderUnavailable(
                "Os Correios demoraram para responder. Tente novamente."
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise FreightAuthenticationError() from exc
            raise FreightProviderUnavailable(
                "Os Correios estao indisponiveis. Tente novamente."
            ) from exc
        except httpx.RequestError as exc:
            raise FreightProviderUnavailable(
                "Nao foi possivel conectar aos Correios."
            ) from exc

        price_str = (
            data.get("pcFinal")
            or data.get("precoFinal")
            or data.get("vlPreco")
            or data.get("valor")
            or "0"
        )
        price_value = _parse_price(price_str)
        return price_value

    def _get_deadline(
        self,
        headers: dict,
        service_code: str,
        package: PackageData,
    ) -> int | None:
        url = (
            f"{CORREIOS_API_BASE}/prazo/v1/nacional/{service_code}"
            f"?cepOrigem={self._config.cep_origem}"
            f"&cepDestino={package.destination_zip_code}"
        )

        try:
            response = httpx.get(
                url,
                headers=headers,
                timeout=httpx.Timeout(
                    connect=self._config.connect_timeout,
                    read=self._config.read_timeout,
                ),
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return None

        days = data.get("prazoEntrega") or data.get("prazo") or data.get("dias") or 0
        return int(days) if days else None


def _parse_price(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(float(value) * 100)

    if isinstance(value, str):
        cleaned = value.replace(".", "").replace(",", ".")
        try:
            return int(float(cleaned) * 100)
        except (ValueError, TypeError):
            return 0

    return 0
