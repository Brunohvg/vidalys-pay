"""Pagar.me webhook payload normalizer.

Extracts structured data from raw webhook payloads without relying
on KeyError-prone direct dict access.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FailureReason:
    """Structured failure reason from payment decline."""
    raw_code: str | None = None
    raw_message: str | None = None
    category: str = "unknown"
    public_message: str = "pagamento não autorizado pela instituição responsável"


@dataclass(frozen=True)
class NormalizedEvent:
    """Normalized webhook event from Pagar.me."""
    event_id: str
    event_type: str
    resource_type: str = ""
    payment_link_id: str | None = None
    checkout_id: str | None = None
    order_id: str | None = None
    order_code: str | None = None
    charge_id: str | None = None
    transaction_id: str | None = None
    internal_payment_link_id: str | None = None
    internal_boleto_id: str | None = None
    status: str | None = None
    charge_status: str | None = None
    transaction_status: str | None = None
    amount_cents: int | None = None
    installments: int | None = None
    payment_method: str | None = None
    failure: FailureReason = field(default_factory=FailureReason)


def normalize_event(payload: dict[str, Any]) -> NormalizedEvent:
    """Normalize a Pagar.me webhook payload into structured data."""
    event_id = payload.get("id", "")
    event_type = payload.get("type", "")

    resource_type = event_type.split(".")[0] if "." in event_type else ""

    data = payload.get("data", {})
    if not isinstance(data, dict):
        data = {}

    return NormalizedEvent(
        event_id=event_id,
        event_type=event_type,
        resource_type=resource_type,
        payment_link_id=_extract_payment_link_id(data),
        checkout_id=_extract_checkout_id(data),
        order_id=_extract_order_id(data, resource_type),
        order_code=_optional_text(data.get("code")),
        charge_id=_extract_charge_id(data, resource_type),
        transaction_id=_extract_transaction_id(data, resource_type),
        internal_payment_link_id=_extract_internal_id(data),
        internal_boleto_id=_extract_metadata_value(data, "internal_boleto_id"),
        status=_optional_text(data.get("status")),
        charge_status=_extract_charge_status(data, resource_type),
        transaction_status=_extract_transaction_status(data, resource_type),
        amount_cents=_extract_amount(data),
        installments=_extract_installments(data),
        payment_method=_extract_payment_method(data),
        failure=_extract_failure(data),
    )


def _extract_payment_link_id(data: dict) -> str | None:
    return _optional_text(_as_dict(data.get("payment_link")).get("id"))


def _extract_checkout_id(data: dict) -> str | None:
    return _optional_text(_as_dict(data.get("checkout")).get("id"))


def _extract_order_id(data: dict, resource_type: str) -> str | None:
    oid = _optional_text(_as_dict(data.get("order")).get("id"))
    if oid:
        return oid
    if resource_type == "order":
        return _optional_text(data.get("id"))
    return None


def _extract_charge_id(data: dict, resource_type: str) -> str | None:
    charges = data.get("charges", [])
    if isinstance(charges, list) and charges:
        return _optional_text(_as_dict(charges[0]).get("id"))
    if resource_type == "charge":
        return _optional_text(data.get("id"))
    return None


def _extract_transaction_id(data: dict, resource_type: str) -> str | None:
    charge = _get_first_charge(data)
    if charge:
        last_txn = charge.get("last_transaction", {})
        if isinstance(last_txn, dict):
            return _optional_text(last_txn.get("id"))
    if resource_type == "charge":
        last_txn = data.get("last_transaction", {})
        if isinstance(last_txn, dict):
            return _optional_text(last_txn.get("id"))
    return None


def _extract_charge_status(data: dict, resource_type: str) -> str | None:
    charge = _get_first_charge(data)
    if charge:
        return _optional_text(charge.get("status"))
    if resource_type == "charge":
        return _optional_text(data.get("status"))
    return None


def _extract_transaction_status(data: dict, resource_type: str) -> str | None:
    charge = _get_first_charge(data)
    if charge:
        return _optional_text(_as_dict(charge.get("last_transaction")).get("status"))
    if resource_type == "charge":
        return _optional_text(_as_dict(data.get("last_transaction")).get("status"))
    return None


def _extract_internal_id(data: dict) -> str | None:
    metadata = data.get("metadata", {})
    if isinstance(metadata, dict):
        iid = _optional_text(metadata.get("internal_payment_link_id"))
        if iid:
            return iid

    order_metadata = _as_dict(data.get("order")).get("metadata", {})
    if isinstance(order_metadata, dict):
        iid = _optional_text(order_metadata.get("internal_payment_link_id"))
        if iid:
            return iid

    charge = _get_first_charge(data)
    if charge:
        charge_meta = charge.get("metadata", {})
        if isinstance(charge_meta, dict):
            iid = _optional_text(charge_meta.get("internal_payment_link_id"))
            if iid:
                return iid

    return None


def _extract_metadata_value(data: dict, key: str) -> str | None:
    """Read metadata consistently from order, charge or nested order payloads."""
    nested_order = _as_dict(data.get("order"))
    candidates = [
        data.get("metadata", {}),
        nested_order.get("metadata", {}),
    ]
    charge = _get_first_charge(data)
    if charge:
        candidates.append(charge.get("metadata", {}))

    for metadata in candidates:
        if isinstance(metadata, dict):
            value = metadata.get(key)
            normalized = _optional_text(value)
            if normalized:
                return normalized
    return None


def _get_first_charge(data: dict) -> dict | None:
    charges = data.get("charges", [])
    if isinstance(charges, list) and charges and isinstance(charges[0], dict):
        return charges[0]
    return None


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _optional_text(value: object, max_length: int = 120) -> str | None:
    if not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    if not text or len(text) > max_length:
        return None
    return text


def _extract_amount(data: dict) -> int | None:
    amount = data.get("amount")
    if amount is not None:
        return amount

    charge = _get_first_charge(data)
    if charge:
        amount = charge.get("amount")
        if amount is not None:
            return amount

    return None


def _extract_installments(data: dict) -> int | None:
    charge = _get_first_charge(data)
    if charge:
        last_txn = charge.get("last_transaction", {})
        if isinstance(last_txn, dict):
            i = last_txn.get("installments")
            if i is not None:
                return i

    txn = data.get("last_transaction", {})
    if isinstance(txn, dict):
        i = txn.get("installments")
        if i is not None:
            return i

    return None


def _extract_payment_method(data: dict) -> str | None:
    charge = _get_first_charge(data)
    if charge:
        method = charge.get("payment_method")
        if method:
            return method

    last_txn = data.get("last_transaction", {})
    if isinstance(last_txn, dict):
        method = last_txn.get("payment_method")
        if method:
            return method

    return None


def _extract_failure(data: dict) -> FailureReason:
    """Extract structured failure reason from payload."""
    charge = _get_first_charge(data)
    txn = {}
    if charge:
        txn = charge.get("last_transaction", {})
        if not isinstance(txn, dict):
            txn = {}
    else:
        txn = data.get("last_transaction", {})
        if not isinstance(txn, dict):
            txn = {}

    gateway = txn.get("gateway_response", {})
    if not isinstance(gateway, dict):
        gateway = {}

    raw_code = gateway.get("code", "")
    raw_message = gateway.get("message", "")

    acquirer_code = txn.get("acquirer_response_code", "")
    acquirer_message = txn.get("acquirer_response_message", "")
    txn_status = txn.get("status", "")

    best_code = raw_code or acquirer_code or ""
    best_message = raw_message or acquirer_message or ""

    category = _categorize_failure(best_code, best_message, txn_status)
    public_message = _public_failure_message(category, best_message)

    return FailureReason(
        raw_code=best_code or None,
        raw_message=best_message or None,
        category=category,
        public_message=public_message,
    )


def _categorize_failure(code: str, message: str, txn_status: str) -> str:
    code_lower = code.lower()
    msg_lower = message.lower()

    if "insufficient" in msg_lower or "limit" in code_lower:
        return "insufficient_limit"
    if "invalid" in code_lower and "card" in msg_lower:
        return "invalid_card"
    if "expired" in msg_lower or "expired" in code_lower:
        return "expired_card"
    if "security" in msg_lower or "cvv" in msg_lower or "cvc" in msg_lower:
        return "invalid_security_code"
    if "unavailable" in msg_lower or txn_status == "timeout":
        return "issuer_unavailable"
    if "antifraud" in code_lower or "fraud" in msg_lower:
        return "antifraud_rejected"
    if "not_authorized" in msg_lower or "refused" in msg_lower:
        return "not_authorized"
    if txn_status == "processing_error":
        return "processing_error"
    if code or message:
        return "not_authorized"
    return "unknown"


def _public_failure_message(category: str, raw_message: str) -> str:
    messages = {
        "insufficient_limit": "saldo ou limite insuficiente.",
        "invalid_card": "cartão inválido.",
        "expired_card": "cartão vencido.",
        "invalid_security_code": "código de segurança incorreto.",
        "issuer_unavailable": "instituição financeira indisponível.",
        "antifraud_rejected": "pagamento não autorizado pelo antifraude.",
        "processing_error": "erro temporário no processamento.",
        "not_authorized": "pagamento não autorizado pela instituição responsável.",
        "unknown": "pagamento não autorizado pela instituição responsável.",
    }

    prefix = messages.get(category, messages["unknown"])

    if raw_message and len(raw_message) < 100 and raw_message.lower() not in prefix.lower():
        return f"{prefix} ({raw_message})"
    return prefix
