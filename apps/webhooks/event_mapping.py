"""Webhook event mapping — versioned mapping table for Pagar.me events.

Designed for payment link use case (auth_and_capture credit card).
Recommended webhook events to register: order.paid, order.payment_failed, charge.refunded.
"""

EVENT_MAP = {
    # Order events (primary: use these in webhook registration)
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
        "description": "Pedido criado",
    },
    "order.closed": {
        "action": "mark_expired",
        "link_status": "EXPIRED",
        "description": "Pedido fechado/expirado",
    },
    "order.updated": {
        "action": "ignore",
        "description": "Pedido atualizado",
    },

    # Charge events (secondary: may overlap with order events)
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
        "action": "ignore",
        "description": "Cobrança pendente",
    },
    "charge.processing": {
        "action": "ignore",
        "description": "Cobrança processando",
    },
    "charge.chargedback": {
        "action": "create_attempt",
        "attempt_status": "CHARGEDBACK",
        "description": "Chargeback",
    },
    "charge.updated": {
        "action": "ignore",
        "description": "Cobrança atualizada",
    },
    "charge.created": {
        "action": "ignore",
        "description": "Cobrança criada",
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
        "description": "Antifraude manual",
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
        "action": "mark_expired",
        "link_status": "EXPIRED",
        "description": "Checkout cancelado",
    },
    "checkout.closed": {
        "action": "mark_expired",
        "link_status": "EXPIRED",
        "description": "Checkout fechado",
    },
}

# States that are considered final
FINAL_STATES = {"PAID", "CANCELED", "EXPIRED", "REFUNDED"}

# States that should never be regressed
NO_REGRESS_STATES = {"PAID", "REFUNDED"}


def get_event_config(event_type: str) -> dict | None:
    return EVENT_MAP.get(event_type)


def is_final_state(status: str) -> bool:
    return status in FINAL_STATES
