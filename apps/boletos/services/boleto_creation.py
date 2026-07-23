"""Idempotent boleto creation using the existing Pagar.me client."""
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.boletos.models import Boleto, BoletoStatus, Company
from apps.boletos.validators import normalize_cnpj, validate_cnpj
from apps.integrations.pagarme.client import PagarmeClient, PagarmeError
from apps.sellers.models import Seller

logger = logging.getLogger("apps.boletos")


@dataclass(frozen=True)
class BoletoCreationData:
    cnpj: str
    legal_name: str
    trade_name: str
    email: str
    phone: str
    whatsapp_phone: str
    zip_code: str
    street: str
    number: str
    complement: str
    district: str
    city: str
    state: str
    amount_cents: int
    due_date: date
    description: str
    internal_reference: str = ""
    internal_notes: str = ""


@dataclass(frozen=True)
class CreateBoletoResult:
    boleto: Boleto | None
    success: bool
    error_message: str = ""
    uncertain: bool = False
    idempotent_replay: bool = False


def create_boleto(
    *,
    seller: Seller,
    actor_user=None,
    actor_seller: Seller | None = None,
    data: BoletoCreationData,
    idempotency_key: str,
    client: PagarmeClient | None = None,
    reissued_from: Boleto | None = None,
) -> CreateBoletoResult:
    """Create a local attempt first, then one Pagar.me order."""
    validation_error = _validate_creation(seller, actor_user, actor_seller, data, idempotency_key)
    if validation_error:
        return CreateBoletoResult(None, False, validation_error)

    snapshot = _company_snapshot(data)
    request_summary = _request_summary(data, snapshot)
    if reissued_from:
        if reissued_from.seller_id != seller.id:
            return CreateBoletoResult(None, False, "Boleto original pertence a outro vendedor.")
        request_summary["reissued_from_id"] = str(reissued_from.id)
    payload_hash = _payload_hash(request_summary)

    existing = Boleto.objects.filter(
        seller=seller,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return _existing_result(existing, payload_hash)

    try:
        with transaction.atomic():
            company = _get_or_create_company(data)
            boleto = Boleto.objects.create(
                seller=seller,
                company=company,
                reissued_from=reissued_from,
                created_by_user=actor_user,
                created_by_seller=actor_seller,
                amount_cents=data.amount_cents,
                due_date=data.due_date,
                description=data.description,
                internal_reference=data.internal_reference,
                internal_notes=data.internal_notes,
                status=BoletoStatus.CREATING,
                idempotency_key=idempotency_key,
                company_snapshot=snapshot,
                creation_request={
                    **request_summary,
                    "payload_hash": payload_hash,
                },
            )
    except IntegrityError:
        existing = Boleto.objects.filter(
            seller=seller,
            idempotency_key=idempotency_key,
        ).first()
        if existing:
            return _existing_result(existing, payload_hash)
        raise

    provider_client = client or PagarmeClient()
    provider_started_at = time.monotonic()
    try:
        response = provider_client.create_boleto_order(
            code=f"BOL-{boleto.id}",
            amount_cents=boleto.amount_cents,
            description=boleto.description,
            due_date=boleto.due_date.isoformat(),
            customer=_pagarme_customer(snapshot),
            metadata={
                "aggregate_type": "boleto",
                "internal_boleto_id": str(boleto.id),
                "seller_id": str(seller.id),
                "reference": boleto.internal_reference,
            },
            idempotency_key=idempotency_key,
        )
    except PagarmeError as exc:
        logger.warning(
            "boleto_creation_provider_error=true boleto=%s seller=%s status=%s duration_ms=%d",
            boleto.id,
            seller.id,
            exc.status_code,
            (time.monotonic() - provider_started_at) * 1000,
        )
        if exc.status_code >= 500:
            return _mark_unknown(boleto)
        boleto.status = BoletoStatus.CREATION_ERROR
        boleto.creation_response = {
            "provider_error": True,
            "status_code": exc.status_code,
        }
        boleto.save(update_fields=["status", "creation_response", "updated_at"])
        return CreateBoletoResult(
            boleto,
            False,
            "Não foi possível emitir o boleto. Revise os dados e tente novamente.",
        )
    except Exception:
        logger.exception(
            "boleto_creation_unknown=true boleto=%s seller=%s duration_ms=%d",
            boleto.id,
            seller.id,
            (time.monotonic() - provider_started_at) * 1000,
        )
        return _mark_unknown(boleto)

    parsed = _parse_provider_response(response)
    if not parsed["order_id"] or not parsed["charge_id"]:
        logger.warning(
            "boleto_creation_incomplete=true boleto=%s seller=%s duration_ms=%d",
            boleto.id,
            seller.id,
            (time.monotonic() - provider_started_at) * 1000,
        )
        return _mark_unknown(boleto, parsed)

    boleto.provider_order_id = parsed["order_id"]
    boleto.provider_charge_id = parsed["charge_id"]
    boleto.provider_transaction_id = parsed["transaction_id"] or None
    boleto.provider_status = parsed["provider_status"]
    boleto.digitable_line = parsed["digitable_line"]
    boleto.barcode = parsed["barcode"]
    boleto.pdf_url = parsed["pdf_url"]
    boleto.status = BoletoStatus.PENDING
    boleto.creation_response = parsed
    boleto.save(
        update_fields=[
            "provider_order_id",
            "provider_charge_id",
            "provider_transaction_id",
            "provider_status",
            "digitable_line",
            "barcode",
            "pdf_url",
            "status",
            "creation_response",
            "updated_at",
        ]
    )
    transaction.on_commit(
        lambda boleto_id=boleto.id: _queue_created_notification(boleto_id),
        robust=True,
    )
    logger.info(
        "boleto_creation_success=true boleto=%s seller=%s order=%s charge=%s duration_ms=%d",
        boleto.id,
        seller.id,
        boleto.provider_order_id,
        boleto.provider_charge_id,
        (time.monotonic() - provider_started_at) * 1000,
    )
    return CreateBoletoResult(boleto, True)


def _queue_created_notification(boleto_id) -> None:
    from apps.notifications.push_service import queue_boleto_status_push
    from apps.notifications.whatsapp_service import queue_boleto_created

    boleto = Boleto.objects.select_related("seller").get(pk=boleto_id)
    queue_boleto_created(boleto=boleto)
    queue_boleto_status_push(boleto=boleto, event_type="boleto_created")


def _validate_creation(seller, actor_user, actor_seller, data, idempotency_key) -> str:
    try:
        validate_cnpj(data.cnpj)
    except Exception:
        return "CNPJ inválido."
    if not seller.is_active:
        return "Vendedor inativo."
    if bool(actor_user) == bool(actor_seller):
        return "Ator criador inválido."
    if actor_user and not (
        isinstance(actor_user, get_user_model())
        and actor_user.is_authenticated
        and actor_user.is_superuser
    ):
        return "Gestor não autorizado."
    if actor_seller and actor_seller.pk != seller.pk:
        return "O vendedor não pode criar boleto para outro vendedor."
    if data.amount_cents <= 0:
        return "O valor deve ser maior que zero."
    if data.amount_cents > seller.max_payment_amount_cents:
        return "O valor excede o limite do vendedor."
    if data.due_date < date.today():
        return "O vencimento não pode estar no passado."
    if not idempotency_key or len(idempotency_key) > 100:
        return "Chave de idempotência inválida."
    return ""


def _get_or_create_company(data: BoletoCreationData) -> Company:
    cnpj = normalize_cnpj(data.cnpj)
    defaults = {
        "legal_name": data.legal_name,
        "trade_name": data.trade_name,
        "email": data.email,
        "phone": data.phone,
        "whatsapp_phone": data.whatsapp_phone,
        "zip_code": re.sub(r"\D", "", data.zip_code),
        "street": data.street,
        "number": data.number,
        "complement": data.complement,
        "district": data.district,
        "city": data.city,
        "state": data.state.upper(),
    }
    company, created = Company.objects.get_or_create(cnpj=cnpj, defaults=defaults)
    if not created:
        for field, value in defaults.items():
            setattr(company, field, value)
        company.save(update_fields=[*defaults, "updated_at"])
    return company


def _company_snapshot(data: BoletoCreationData) -> dict:
    return {
        "cnpj": normalize_cnpj(data.cnpj),
        "legal_name": data.legal_name,
        "trade_name": data.trade_name,
        "email": data.email,
        "phone": re.sub(r"\D", "", data.phone),
        "whatsapp_phone": re.sub(r"\D", "", data.whatsapp_phone),
        "address": {
            "zip_code": re.sub(r"\D", "", data.zip_code),
            "street": data.street,
            "number": data.number,
            "complement": data.complement,
            "district": data.district,
            "city": data.city,
            "state": data.state.upper(),
            "country": "BR",
        },
    }


def _request_summary(data: BoletoCreationData, snapshot: dict) -> dict:
    return {
        "company": snapshot,
        "amount_cents": data.amount_cents,
        "due_date": data.due_date.isoformat(),
        "description": data.description,
        "internal_reference": data.internal_reference,
    }


def _payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _existing_result(boleto: Boleto, payload_hash: str) -> CreateBoletoResult:
    if boleto.creation_request.get("payload_hash") != payload_hash:
        return CreateBoletoResult(
            None,
            False,
            "Chave de idempotência reutilizada com dados diferentes.",
        )
    return CreateBoletoResult(
        boleto,
        boleto.status not in {BoletoStatus.CREATION_ERROR},
        "A emissão anterior não foi concluída." if boleto.status == BoletoStatus.CREATION_ERROR else "",
        uncertain=boleto.status == BoletoStatus.CREATION_UNKNOWN,
        idempotent_replay=True,
    )


def _pagarme_customer(snapshot: dict) -> dict:
    address = snapshot["address"]
    customer = {
        "name": snapshot["legal_name"],
        "email": snapshot["email"],
        "type": "company",
        "document": snapshot["cnpj"],
        "document_type": "CNPJ",
        "address": {
            "line_1": f"{address['number']}, {address['street']}, {address['district']}",
            "line_2": address["complement"],
            "zip_code": address["zip_code"],
            "city": address["city"],
            "state": address["state"],
            "country": "BR",
        },
    }
    phone = snapshot["phone"] or snapshot["whatsapp_phone"]
    if len(phone) in {10, 11}:
        customer["phones"] = {
            "mobile_phone": {
                "country_code": "55",
                "area_code": phone[:2],
                "number": phone[2:],
            }
        }
    return customer


def _parse_provider_response(response: dict) -> dict:
    if not isinstance(response, dict):
        return _empty_provider_response()
    charges = response.get("charges") or []
    charge = charges[0] if isinstance(charges, list) and charges else {}
    if not isinstance(charge, dict):
        charge = {}
    transaction_data = charge.get("last_transaction") or {}
    if not isinstance(transaction_data, dict):
        transaction_data = {}
    return {
        "order_id": _bounded_text(response.get("id"), 100),
        "charge_id": _bounded_text(charge.get("id"), 100),
        "transaction_id": _bounded_text(transaction_data.get("id"), 100),
        "provider_status": _bounded_text(
            charge.get("status") or response.get("status"),
            80,
        ),
        "digitable_line": _bounded_digits(transaction_data.get("line"), 120),
        "barcode": _bounded_digits(transaction_data.get("barcode"), 120),
        "pdf_url": _safe_provider_url(
            transaction_data.get("pdf") or transaction_data.get("url")
        ),
    }


def _empty_provider_response() -> dict:
    return {
        "order_id": "",
        "charge_id": "",
        "transaction_id": "",
        "provider_status": "",
        "digitable_line": "",
        "barcode": "",
        "pdf_url": "",
    }


def _bounded_text(value, max_length: int) -> str:
    if not isinstance(value, (str, int)):
        return ""
    text = str(value).strip()
    return text if len(text) <= max_length else ""


def _bounded_digits(value, max_length: int) -> str:
    if not isinstance(value, (str, int)):
        return ""
    digits = re.sub(r"\D", "", str(value))
    return digits if len(digits) <= max_length else ""


def _safe_provider_url(value) -> str:
    if not isinstance(value, str) or len(value) > 500:
        return ""
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return ""
    return parsed.geturl()


def _mark_unknown(boleto: Boleto, summary: dict | None = None) -> CreateBoletoResult:
    boleto.status = BoletoStatus.CREATION_UNKNOWN
    boleto.creation_response = summary or {"result": "unknown"}
    boleto.save(update_fields=["status", "creation_response", "updated_at"])
    return CreateBoletoResult(
        boleto,
        True,
        "Estamos confirmando a emissão. Não tente criar outro boleto.",
        uncertain=True,
    )
