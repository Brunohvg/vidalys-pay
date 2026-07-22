"""Correios CWS (Web Services) client.

Authentication: HTTP Basic Auth + Bearer token with cartao only body.
DR is auto-resolved from the token response (not from env vars).
Pricing/Deadline: batch POST queries.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx
from django.core.cache import cache

from .config import (
    DEADLINE_URL,
    DEFAULT_FALLBACK_HEIGHT_CM,
    DEFAULT_FALLBACK_LENGTH_CM,
    DEFAULT_FALLBACK_WIDTH_CM,
    DEFAULT_PRODUCTS,
    MEU_CONTRATO_URL,
    PRICE_URL,
    PRODUCT_LABELS,
    REQUEST_TIMEOUT_SECONDS,
    TOKEN_CACHE_MARGIN_SECONDS,
    TOKEN_URL,
    TOKEN_URL_CARTAO,
    get_correios_config,
)
from .dataclasses import FreightOption, PackageData
from .exceptions import (
    FreightAuthenticationError,
    FreightConfigurationError,
    FreightConnectionError,
    FreightProviderUnavailable,
    FreightTimeoutError,
)

logger = logging.getLogger("apps.freight")

TOKEN_CACHE_KEY = "correios:cws:token"


# ── TTL ──────────────────────────────────────────────────────────────────────

def calculate_token_ttl(expira_em: Any) -> int:
    """Calculate token TTL from expiraEm field.

    Accepts int (seconds) or str (ISO datetime).
    Falls back to 300s.
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


# ── price parsing ────────────────────────────────────────────────────────────

def parse_price_to_cents(value: Any) -> int:
    """Parse price string to cents using Decimal (never float)."""
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


# ── DR resolution ────────────────────────────────────────────────────────────

def resolve_dr(token_data: dict, config, bearer: str) -> str:
    """Auto-resolve DR from token response — never from env var.

    Priority:
    1. token fields (cartaoPostagem.dr / nuDR / nuSe; contrato.dr / nuDR / nuSe)
    2. Meu Contrato API
    3. empty string (omit from price payload)
    """
    candidates = [
        token_data.get("cartaoPostagem", {}).get("dr"),
        token_data.get("cartaoPostagem", {}).get("nuDR"),
        token_data.get("cartaoPostagem", {}).get("nuSe"),
        token_data.get("contrato", {}).get("dr"),
        token_data.get("contrato", {}).get("nuDR"),
        token_data.get("contrato", {}).get("nuSe"),
        token_data.get("dr"),
        token_data.get("nuDR"),
        token_data.get("nuSe"),
    ]

    for value in candidates:
        if value not in (None, ""):
            return str(value)

    if config.cnpj and config.contrato and bearer:
        dr = _fetch_dr_from_meu_contrato(config.cnpj, config.contrato, bearer)
        if dr:
            return dr

    return ""


def _fetch_dr_from_meu_contrato(cnpj: str, contrato: str, bearer: str) -> str:
    """Try Meu Contrato API as DR fallback."""
    url = f"{MEU_CONTRATO_URL}/empresas/{cnpj}/contratos/{contrato}"
    try:
        response = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {bearer}",
                "Accept": "application/json",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        nu_se = data.get("nuSe")
        if nu_se:
            return str(nu_se)
    except Exception:
        logger.warning(
            "meu_contrato_falhou=true cnpj=%s*** contrato=%s***",
            cnpj[:5],
            contrato[:3],
        )
    return ""


# ── logging helpers ──────────────────────────────────────────────────────────

def _sanitize_error_context(response) -> dict:
    """Extract safe, non-secret fields from an error response."""
    try:
        body = response.json()
    except Exception:
        body = {}
    return {
        "status": response.status_code,
        "message": body.get("message"),
        "msgs": body.get("msgs"),
        "path": body.get("path"),
    }


# ── auth client ──────────────────────────────────────────────────────────────

class CorreiosAuthClient:
    def __init__(self):
        self._config = get_correios_config()

    @property
    def _token_url(self) -> str:
        if self._config.cartao_postagem:
            return TOKEN_URL_CARTAO
        return TOKEN_URL

    def get_token_and_data(self) -> dict[str, Any]:
        """Return the full cached token data dict (or authenticate)."""
        cached = cache.get(TOKEN_CACHE_KEY)
        if cached and isinstance(cached, dict) and cached.get("token"):
            return cached

        data = self._authenticate()
        self._cache_token(data)
        return data

    def get_token(self) -> str:
        """Convenience: return just the bearer token string."""
        return self.get_token_and_data()["token"]

    def invalidate_token(self) -> None:
        cache.delete(TOKEN_CACHE_KEY)

    def _authenticate(self) -> dict[str, Any]:
        """Authenticate via HTTP Basic Auth.

        Cartao body contains ONLY {"numero": "<cartao>"} — no contrato or DR.
        """
        auth = httpx.BasicAuth(
            self._config.usuario,
            self._config.codigo_acesso,
        )

        body = None
        if self._config.cartao_postagem:
            body = {"numero": self._config.cartao_postagem}

        try:
            response = httpx.post(
                self._token_url,
                auth=auth,
                json=body,
                headers={"Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            logger.warning("correios_auth_timeout=true")
            raise FreightTimeoutError(
                "Os Correios demoraram para responder. Tente novamente."
            ) from exc
        except httpx.HTTPStatusError as exc:
            ctx = _sanitize_error_context(exc.response)
            if exc.response.status_code in (401, 403):
                logger.warning("correios_auth_unauthorized=true status=%s", ctx["status"])
                raise FreightAuthenticationError(
                    "Não foi possível autenticar nos Correios. Verifique a configuração."
                ) from exc
            logger.warning("correios_auth_error=true %s", ctx)
            raise FreightProviderUnavailable(
                "Os Correios estão indisponíveis. Tente novamente."
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("correios_auth_connection_error=true error_type=%s", type(exc).__name__)
            raise FreightConnectionError(
                "Não foi possível conectar aos Correios."
            ) from exc

        token = data.get("token") or data.get("access_token") or ""
        if not token:
            raise FreightAuthenticationError(
                "Token não encontrado na resposta dos Correios."
            )

        expira_em = data.get("expiraEm") or data.get("expires_in") or 3600
        data["_expires_in"] = calculate_token_ttl(expira_em)

        return data

    def _cache_token(self, token_data: dict[str, Any]) -> None:
        calculated_ttl = token_data.get("_expires_in", 300)
        ttl = max(calculated_ttl - TOKEN_CACHE_MARGIN_SECONDS, 60)
        cache.set(TOKEN_CACHE_KEY, token_data, timeout=ttl)


# ── freight client ───────────────────────────────────────────────────────────

class CorreiosFreightClient:
    def __init__(self):
        self._config = get_correios_config()
        self._auth = CorreiosAuthClient()

    def get_token_and_data(self) -> dict[str, Any]:
        """Return full token data (with _resolved_dr injected)."""
        return self._auth.get_token_and_data()

    def calculate(self, package: PackageData) -> list[FreightOption]:
        """Calculate freight for PAC and SEDEX."""
        token_data = self._auth.get_token_and_data()
        bearer = token_data["token"]

        dr = resolve_dr(token_data, self._config, bearer)
        token_data["_resolved_dr"] = dr

        try:
            prices = self._batch_price(bearer, package, dr)
        except FreightAuthenticationError:
            self._auth.invalidate_token()
            token_data = self._auth.get_token_and_data()
            bearer = token_data["token"]
            dr = resolve_dr(token_data, self._config, bearer)
            token_data["_resolved_dr"] = dr
            prices = self._batch_price(bearer, package, dr)

        try:
            deadlines = self._batch_deadline(bearer, package)
        except Exception:
            deadlines = {}

        options = []
        for service_code in DEFAULT_PRODUCTS:
            service_name = PRODUCT_LABELS.get(service_code, service_code)
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

        if all(o.price_cents == 0 for o in options):
            raise FreightProviderUnavailable(
                "Nenhum valor de PAC ou SEDEX foi encontrado."
            )

        return options

    def _batch_price(
        self,
        bearer: str,
        package: PackageData,
        dr: str,
    ) -> dict[str, int]:
        """Query prices for PAC and SEDEX in a single POST."""
        length = package.length_cm or DEFAULT_FALLBACK_LENGTH_CM
        width = package.width_cm or DEFAULT_FALLBACK_WIDTH_CM
        height = package.height_cm or DEFAULT_FALLBACK_HEIGHT_CM

        parametros: list[dict[str, Any]] = []
        for service_code in DEFAULT_PRODUCTS:
            param: dict[str, Any] = {
                "coProduto": service_code,
                "nuRequisicao": f"preco-{service_code}",
                "cepOrigem": self._config.cep_origem,
                "cepDestino": package.destination_zip_code,
                "psObjeto": str(package.weight_grams),
                "tpObjeto": "2",
                "comprimento": str(length),
                "largura": str(width),
                "altura": str(height),
            }

            if self._config.contrato:
                param["nuContrato"] = self._config.contrato
            if dr:
                param["nuDR"] = dr

            if package.declared_value_cents > 0:
                param["vlDeclarado"] = str(
                    Decimal(str(package.declared_value_cents))
                    / Decimal("100")
                )

            parametros.append(param)

        payload = {
            "idLote": "lote-vidalys-pay",
            "parametrosProduto": parametros,
        }

        try:
            response = httpx.post(
                PRICE_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "Accept": "application/json",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            logger.warning("correios_preco_timeout=true")
            raise FreightTimeoutError(
                "Os Correios demoraram para responder. Tente novamente."
            ) from exc
        except httpx.HTTPStatusError as exc:
            ctx = _sanitize_error_context(exc.response)
            if exc.response.status_code in (401, 403):
                raise FreightAuthenticationError() from exc
            if exc.response.status_code == 400:
                logger.warning("correios_preco_bad_request=true %s", ctx)
                raise FreightProviderUnavailable(
                    "Os Correios recusaram os dados enviados."
                ) from exc
            if exc.response.status_code == 422:
                logger.warning("correios_preco_unprocessable=true %s", ctx)
                raise FreightProviderUnavailable(
                    "Os Correios recusaram os dados do pacote."
                ) from exc
            logger.warning("correios_preco_error=true %s", ctx)
            raise FreightProviderUnavailable(
                "Os Correios estão indisponíveis. Tente novamente."
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("correios_preco_connection_error=true error_type=%s", type(exc).__name__)
            raise FreightConnectionError(
                "Não foi possível conectar aos Correios."
            ) from exc

        return self._parse_price_response(data)

    def _parse_price_response(self, data: Any) -> dict[str, int]:
        """Normalize price response (list or dict) and parse prices."""
        items = data if isinstance(data, list) else [data]
        results: dict[str, int] = {}
        for item in items:
            co_produto = item.get("coProduto", "")
            if not co_produto:
                continue

            if item.get("msgErro") or item.get("txErro"):
                logger.warning(
                    "correios_preco_produto_erro=true coProduto=%s msgErro=%s",
                    co_produto,
                    item.get("msgErro") or item.get("txErro"),
                )
                continue

            price_str = (
                item.get("pcFinal")
                or item.get("precoFinal")
                or item.get("vlPreco")
                or item.get("valor")
                or "0"
            )
            cents = parse_price_to_cents(price_str)
            if cents > 0:
                results[co_produto] = cents

        return results

    def _batch_deadline(
        self,
        bearer: str,
        package: PackageData,
    ) -> dict[str, int]:
        """Query deadlines for PAC and SEDEX in a single POST."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        parametros = []
        for service_code in DEFAULT_PRODUCTS:
            parametros.append({
                "coProduto": service_code,
                "nuRequisicao": f"prazo-{service_code}",
                "cepOrigem": self._config.cep_origem,
                "cepDestino": package.destination_zip_code,
                "dataPostagem": today,
            })

        payload = {
            "idLote": "lote-vidalys-pay",
            "parametrosPrazo": parametros,
        }

        try:
            response = httpx.post(
                DEADLINE_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "Accept": "application/json",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            logger.warning("correios_prazo_timeout=true")
            return {}
        except httpx.HTTPStatusError as exc:
            ctx = _sanitize_error_context(exc.response)
            logger.warning("correios_prazo_error=true %s", ctx)
            return {}
        except httpx.RequestError as exc:
            logger.warning("correios_prazo_connection_error=true error_type=%s", type(exc).__name__)
            return {}

        return self._parse_deadline_response(data)

    def _parse_deadline_response(self, data: Any) -> dict[str, int]:
        """Normalize deadline response and extract delivery days."""
        items = data if isinstance(data, list) else [data]
        results: dict[str, int] = {}
        for item in items:
            co_produto = item.get("coProduto", "")
            if not co_produto:
                continue
            days = (
                item.get("prazoEntrega")
                or item.get("prazo")
                or item.get("dias")
                or 0
            )
            if days:
                results[co_produto] = int(days)
        return results


# ── connection test ──────────────────────────────────────────────────────────

def test_correios_connection() -> dict[str, Any]:
    """End-to-end Correios connectivity test with a real quote."""
    from .config import validate_correios_config

    try:
        config = get_correios_config()
        validate_correios_config(config)
    except FreightConfigurationError as exc:
        return {"success": False, "message": str(exc), "sample": None}

    try:
        client = CorreiosFreightClient()
        token_data = client.get_token_and_data()
        bearer = token_data["token"]
        dr = resolve_dr(token_data, config, bearer)

        test_package = PackageData(
            destination_zip_code=config.cep_origem or "30140071",
            weight_grams=100,
            length_cm="20",
            width_cm="15",
            height_cm="2",
        )
        prices = client._batch_price(bearer, test_package, dr)
    except Exception as exc:
        return {"success": False, "message": str(exc), "sample": None}

    sample = None
    for code, name in PRODUCT_LABELS.items():
        if prices.get(code):
            cents = prices[code]
            sample = {
                "service": name,
                "price_cents": cents,
                "formatted_price": f"R$ {cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            }
            break

    return {
        "success": sample is not None,
        "message": "Correios conectado — cotação oficial funcionando." if sample else "Nenhum preço obtido.",
        "sample": sample,
    }
