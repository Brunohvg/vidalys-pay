"""Webhook event mapping — versioned mapping table for Pagar.me events."""

# Event mapping: event_type → action config
# Actions: mark_paid, create_attempt, update_attempt, mark_canceled, mark_refunded, ignore
EVENT_MAP = {
    # Order events
    "order.paid": {
        "action": "mark_paid",
        "link_status": "PAID",
        "attempt_status": "PAID",
        "description": "Pedido pago",
    },
    "order.payment_failed": {
        "action": "create_attempt",
        "attempt_status": "FAILED",
        "description": "Falha no pagamento do pedido",
    },
    "order.canceled": {
        "action": "mark_canceled",
        "link_status": "CANCELED",
        "description": "Pedido cancelado",
    },
    "order.created": {
        "action": "ignore",
        "description": "Pedido criado (já tratado na criação do link)",
    },
    "order.closed": {
        "action": "ignore_if_final",
        "description": "Pedido fechado",
    },
    "order.updated": {
        "action": "ignore",
        "description": "Pedido atualizado",
    },
    # Charge events
    "charge.paid": {
        "action": "create_attempt",
        "attempt_status": "PAID",
        "description": "Cobrança paga",
    },
    "charge.payment_failed": {
        "action": "create_attempt",
        "attempt_status": "FAILED",
        "description": "Falha na cobrança",
    },
    "charge.refunded": {
        "action": "mark_refunded",
        "link_status": "REFUNDED",
        "attempt_status": "REFUNDED",
        "description": "Cobrança estornada",
    },
    "charge.pending": {
        "action": "create_attempt",
        "attempt_status": "PENDING",
        "description": "Cobrança pendente",
    },
    "charge.processing": {
        "action": "create_attempt",
        "attempt_status": "PROCESSING",
        "description": "Cobrança processando",
    },
    "charge.chargedback": {
        "action": "create_attempt",
        "attempt_status": "CHARGEDBACK",
        "description": "Chargeback na cobrança",
    },
    "charge.underpaid": {
        "action": "ignore",
        "description": "Cobrança paga a menos",
    },
    "charge.overpaid": {
        "action": "ignore",
        "description": "Cobrança paga a mais",
    },
    "charge.partial_canceled": {
        "action": "ignore",
        "description": "Cobrança parcialmente cancelada",
    },
    "charge.antifraud_approved": {
        "action": "ignore",
        "description": "Antifraude aprovado",
    },
    "charge.antifraud_reproved": {
        "action": "ignore",
        "description": "Antifraude reprovado",
    },
    "charge.antifraud_manual": {
        "action": "ignore",
        "description": "Antifraude análise manual",
    },
    "charge.antifraud_pending": {
        "action": "ignore",
        "description": "Antifraude pendente",
    },
    # Checkout events
    "checkout.created": {
        "action": "ignore",
        "description": "Checkout criado",
    },
    "checkout.canceled": {
        "action": "ignore_if_final",
        "description": "Checkout cancelado",
    },
    "checkout.closed": {
        "action": "ignore_if_final",
        "description": "Checkout fechado",
    },
    # Charge events (legacy)
    "charge.created": {
        "action": "ignore",
        "description": "Cobrança criada",
    },
    "charge.updated": {
        "action": "ignore",
        "description": "Cobrança atualizada",
    },
}

# States that are considered final (no further transitions)
FINAL_STATES = {"PAID", "CANCELED", "EXPIRED", "REFUNDED"}

# States that should not be regressed
NO_REGRESS_STATES = {"PAID", "REFUNDED"}


def get_event_config(event_type: str) -> dict | None:
    """Get configuration for an event type."""
    return EVENT_MAP.get(event_type)


def is_final_state(status: str) -> bool:
    """Check if a status is final."""
    return status in FINAL_STATES


def can_transition(current_status: str, new_status: str) -> bool:
    """Check if a state transition is allowed.

    Rules:
    - Never regress from PAID or REFUNDED
    - Never go from CANCELED or EXPIRED to ACTIVE
    - FAILED attempts don't close the link
    """
    if current_status in NO_REGRESS_STATES:
        return False
    return not (current_status in ("CANCELED", "EXPIRED") and new_status == "ACTIVE")
