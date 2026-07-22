"""Correios CWS (Web Services) client.

Authentication: HTTP Basic Auth + Bearer token.
Pricing/Deadline: batch POST queries.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
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


def calculate_token_ttl(expira_em: Any) -> int:
    """Calculate token TTL from expiraEm field.

    expira_em can be:
    - int: seconds until expiry
    - str: ISO datetime string
    """
    if isinstance(expira_em, int):
        return expira_em

    if isinstance(expira_em, str):
        try:
            expires_at = datetime.fromisoformat(
                expira_em.replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            return max(int((expires_at - now).total_seconds()), 60)
        except (ValueError, TypeError):
            return 300

    return 300


class CorreiosAuthClient:
    def __init__(self):
        self._config = get_correios_config()

    @property
    def _token_url(self) -> str:
        if self._config.cartao_postagem:
            return f"{CORREIOS_API_BASE}/token/v1/autentica/cartaopostagem"
        return f"{CORREIOS_API_BASE}/token/v1/autentica"

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
        """Authenticate using HTTP Basic Auth.

        When cartao_postagem is set, sends numero, contrato, and dr in body.
        """
        auth = httpx.BasicAuth(
            self._config.usuario,
            self._config.codigo_acesso,
        )

        body = None
        if self._config.cartao_postagem != "":
            body: dict[str, Any] = {
                "numero": self._config.cartao_postagem,
            }
            if self._config.contrato != "":
                body["contrato"] = self._config.contrato
            if self._config.dr != "":
                dr_value = _parse_dr(self._config.dr)
                if dr_value is not None:
                    body["dr"] = dr_value

        timeout = httpx.Timeout(
            self._config.connect_timeout,
            read=self._config.read_timeout,
        )

        try:
            response = httpx.post(
                self._token_url,
                auth=auth,
                json=body,
                headers={"Accept": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            logger.warning(
                "autenticacao_correios_timeout=true connect=%s read=%s",
                self._config.connect_timeout,
                self._config.read_timeout,
            )
            raise FreightProviderUnavailable(
                "Os Correios demoraram para responder. Tente novamente."
            ) from exc
        except httpx.HTTPStatusError as exc:
            self._log_http_error("autenticacao", exc)
            if exc.response.status_code in (401, 403):
                raise FreightAuthenticationError(
                    "Não foi possível autenticar nos Correios. Verifique a configuração."
                ) from exc
            raise FreightProviderUnavailable(
                "Os Correios estão indisponíveis. Tente novamente."
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(
                "autenticacao_correios_request_error=true error_type=%s",
                type(exc).__name__,
            )
            raise FreightProviderUnavailable(
                "Não foi possível conectar aos Correios."
            ) from exc

        token = data.get("token") or data.get("access_token") or ""
        expira_em = data.get("expiraEm") or data.get("expires_in") or 3600

        if not token:
            raise FreightAuthenticationError(
                "Token não encontrado na resposta dos Correios."
            )

        expires_in = calculate_token_ttl(expira_em)

        return CorreiosToken(
            access_token=token,
            expires_in=expires_in,
            token_type=data.get("tipo", "Bearer"),
        )

    def _cache_token(self, token_data: CorreiosToken) -> None:
        ttl = max(60, token_data.expires_in - self._config.token_cache_margin_seconds)
        cache.set(
            TOKEN_CACHE_KEY,
            {"access_token": token_data.access_token},
            timeout=ttl,
        )


def _parse_dr(value: str) -> int | None:
    """Parse DR field to int, returning None if invalid."""
    if not value or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning("correios_dr_invalido=true dr_value=%s", value)
        return None


def _sanitize_response_text(text: str, max_length: int = 300) -> str:
    """Remove sensitive data before logging."""
    sanitized = text or ""
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
    return sanitized


def _log_http_error(etapa: str, exc: httpx.HTTPStatusError, co_produto: str | None = None) -> None:
    """Log HTTP errors with sanitized context."""
    extra: dict[str, Any] = {
        "etapa": etapa,
        "http_status": exc.response.status_code,
        "response_text": _sanitize_response_text(exc.response.text),
    }
    if co_produto:
        extra["coProduto"] = co_produto
    logger.warning("correios_http_error=true %s", extra)


def _parse_price(value: Any) -> int:
    """Parse price string to cents using Decimal for precision."""
    if isinstance(value, Decimal):
        return int(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)

    if isinstance(value, (int, float)):
        return int(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)

    if isinstance(value, str):
        normalized = value.strip().replace(",", ".")
        try:
            return int(Decimal(normalized).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)
        except Exception:
            return 0

    return 0


class CorreiosFreightClient:
    SERVICE_NAMES = {
        "03298": "PAC",
        "03220": "SEDEX",
    }

    def __init__(self):
        self._config = get_correios_config()
        self._auth = CorreiosAuthClient()

    def calculate(self, package: PackageData) -> list[FreightOption]:
        """Calculate freight using batch POST endpoints for price and deadline."""
        services = [
            self._config.pac_product_code,
            self._config.sedex_product_code,
        ]

        token = self._auth.get_token()

        try:
            prices = self._batch_price(token, services, package)
        except FreightAuthenticationError:
            self._auth.invalidate_token()
            token = self._auth.get_token()
            prices = self._batch_price(token, services, package)

        try:
            deadlines = self._batch_deadline(token, services, package)
        except (FreightProviderUnavailable, FreightAuthenticationError):
            deadlines = {}

        options = []
        for service_code in services:
            service_name = self.SERVICE_NAMES.get(service_code, service_code)
            price_cents = prices.get(service_code, 0)
            delivery_days = deadlines.get(service_code)

            options.append(FreightOption(
                provider="correios",
                service_code=service_code,
                service_name=service_name,
                price_cents=price_cents,
                delivery_days=delivery_days,
                official=price_cents > 0,
                error="Preço indisponível" if price_cents == 0 else None,
            ))

        return options

    def _batch_price(
        self,
        token: str,
        services: list[str],
        package: PackageData,
    ) -> dict[str, int]:
        """Query prices for all services in a single POST."""
        url = f"{CORREIOS_API_BASE}/preco/v1/nacional"

        parametros = []
        for i, service_code in enumerate(services):
            param: dict[str, Any] = {
                "coProduto": service_code,
                "nuRequisicao": f"preco-{service_code}",
                "cepOrigem": self._config.cep_origem,
                "cepDestino": package.destination_zip_code,
                "psObjeto": str(package.weight_grams),
                "tpObjeto": "2",
                "comprimento": str(package.length_cm),
                "largura": str(package.width_cm),
                "altura": str(package.height_cm),
            }

            if self._config.contrato != "":
                param["nuContrato"] = self._config.contrato
            if self._config.dr != "":
                dr_value = _parse_dr(self._config.dr)
                if dr_value is not None:
                    param["nuDR"] = dr_value

            if package.declared_value_cents > 0:
                param["vlDeclarado"] = str(
                    Decimal(str(package.declared_value_cents))
                    / Decimal("100")
                )

            parametros.append(param)

        payload = {
            "idLote": "freight-batch",
            "parametrosProduto": parametros,
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        try:
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=httpx.Timeout(
                    self._config.connect_timeout,
                    read=self._config.read_timeout,
                ),
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            logger.warning(
                "preco_correios_timeout=true connect=%s read=%s",
                self._config.connect_timeout,
                self._config.read_timeout,
            )
            raise FreightProviderUnavailable(
                "Os Correios demoraram para responder. Tente novamente."
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise FreightAuthenticationError() from exc
            _log_http_error("preco", exc)
            raise FreightProviderUnavailable(
                "Os Correios estão indisponíveis. Tente novamente."
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(
                "preco_correios_request_error=true error_type=%s",
                type(exc).__name__,
            )
            raise FreightProviderUnavailable(
                "Não foi possível conectar aos Correios."
            ) from exc

        results = {}
        if isinstance(data, list):
            for item in data:
                co_produto = item.get("coProduto", "")
                price_str = (
                    item.get("pcFinal")
                    or item.get("precoFinal")
                    or item.get("vlPreco")
                    or item.get("valor")
                    or "0"
                )
                results[co_produto] = _parse_price(price_str)
        elif isinstance(data, dict):
            co_produto = data.get("coProduto", services[0] if services else "")
            price_str = (
                data.get("pcFinal")
                or data.get("precoFinal")
                or data.get("vlPreco")
                or data.get("valor")
                or "0"
            )
            results[co_produto] = _parse_price(price_str)

        return results

    def _batch_deadline(
        self,
        token: str,
        services: list[str],
        package: PackageData,
    ) -> dict[str, int]:
        """Query deadlines for all services in a single POST."""
        url = f"{CORREIOS_API_BASE}/prazo/v1/nacional"

        parametros = []
        today = datetime.now().strftime("%Y-%m-%d")
        for service_code in services:
            parametros.append({
                "coProduto": service_code,
                "nuRequisicao": f"prazo-{service_code}",
                "cepOrigem": self._config.cep_origem,
                "cepDestino": package.destination_zip_code,
                "dataPostagem": today,
            })

        payload = {
            "idLote": "freight-batch",
            "parametrosPrazo": parametros,
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        try:
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=httpx.Timeout(
                    self._config.connect_timeout,
                    read=self._config.read_timeout,
                ),
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            logger.warning(
                "prazo_correios_timeout=true connect=%s read=%s",
                self._config.connect_timeout,
                self._config.read_timeout,
            )
            return {}
        except httpx.HTTPStatusError as exc:
            _log_http_error("prazo", exc)
            return {}
        except httpx.RequestError as exc:
            logger.warning(
                "prazo_correios_request_error=true error_type=%s",
                type(exc).__name__,
            )
            return {}

        results = {}
        if isinstance(data, list):
            for item in data:
                co_produto = item.get("coProduto", "")
                days = item.get("prazoEntrega") or item.get("prazo") or item.get("dias") or 0
                if days:
                    results[co_produto] = int(days)
        elif isinstance(data, dict):
            co_produto = data.get("coProduto", services[0] if services else "")
            days = data.get("prazoEntrega") or data.get("prazo") or data.get("dias") or 0
            if days:
                results[co_produto] = int(days)

        return results
