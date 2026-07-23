"""CNPJ lookup service and provider-independent result."""
from dataclasses import asdict, dataclass
from datetime import datetime

from django.utils.dateparse import parse_datetime

from apps.boletos.gateways.cnpj_provider import BrasilApiCnpjGateway
from apps.boletos.validators import normalize_cnpj, validate_cnpj


@dataclass(frozen=True)
class CompanyLookupResult:
    cnpj: str
    legal_name: str = ""
    trade_name: str = ""
    email: str = ""
    phone: str = ""
    zip_code: str = ""
    street: str = ""
    number: str = ""
    complement: str = ""
    district: str = ""
    city: str = ""
    state: str = ""
    registration_status: str = ""
    source: str = "brasilapi"
    raw_source_updated_at: datetime | None = None

    def as_dict(self) -> dict:
        data = asdict(self)
        if self.raw_source_updated_at:
            data["raw_source_updated_at"] = self.raw_source_updated_at.isoformat()
        return data


def lookup_company(cnpj: object, *, gateway=None) -> CompanyLookupResult:
    """Validate a CNPJ, query BrasilAPI and normalize its response."""
    normalized = normalize_cnpj(cnpj)
    validate_cnpj(normalized)
    provider = gateway or BrasilApiCnpjGateway()
    payload = provider.lookup(normalized)
    return _map_brasilapi_response(normalized, payload)


def _map_brasilapi_response(cnpj: str, payload: dict) -> CompanyLookupResult:
    street_type = _text(payload.get("descricao_tipo_de_logradouro"))
    street_name = _text(payload.get("logradouro"))
    street = f"{street_type} {street_name}".strip() if street_type else street_name

    return CompanyLookupResult(
        cnpj=cnpj,
        legal_name=_text(payload.get("razao_social")),
        trade_name=_text(payload.get("nome_fantasia")),
        email=_text(payload.get("email")),
        phone=_text(payload.get("ddd_telefone_1") or payload.get("telefone")),
        zip_code=normalize_cnpj(payload.get("cep"))[:8],
        street=street,
        number=_text(payload.get("numero")),
        complement=_text(payload.get("complemento")),
        district=_text(payload.get("bairro")),
        city=_text(payload.get("municipio")),
        state=_text(payload.get("uf")).upper()[:2],
        registration_status=_text(
            payload.get("descricao_situacao_cadastral") or payload.get("situacao_cadastral")
        ),
        raw_source_updated_at=_parse_source_datetime(
            payload.get("data_situacao_cadastral") or payload.get("data_inicio_atividade")
        ),
    )


def _text(value: object) -> str:
    return str(value or "").strip()


def _parse_source_datetime(value: object) -> datetime | None:
    if not value:
        return None
    return parse_datetime(str(value))
