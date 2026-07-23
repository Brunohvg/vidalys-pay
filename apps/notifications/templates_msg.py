"""WhatsApp message templates."""
from django.conf import settings


def _brl(cents: int) -> str:
    return f"R$ {cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def invitation_message(*, seller_name: str, activation_url: str) -> str:
    """Template for invitation message."""
    return (
        f"Olá, {seller_name}.\n\n"
        f"Seu acesso ao {settings.APP_NAME} foi liberado:\n"
        f"{activation_url}\n\n"
        f"O link é pessoal, expira em {settings.INVITATION_EXPIRATION_HOURS} horas "
        f"e funciona uma única vez. Não encaminhe esta mensagem."
    )


def payment_link_created_message(
    *,
    reference: str,
    customer_name: str | None,
    amount_cents: int,
    installments: int,
    payment_url: str,
) -> str:
    """Template for payment link created message."""
    amount_formatted = f"R$ {amount_cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    customer_display = customer_name if customer_name else "Não informado"
    installment_label = f"{installments}x sem juros"

    return (
        f"Link de pagamento criado\n\n"
        f"Pedido: {reference}\n"
        f"Cliente: {customer_display}\n"
        f"Valor: {amount_formatted}\n"
        f"Parcelamento: {installment_label}\n\n"
        f"{payment_url}"
    )


def payment_approved_message(
    *,
    reference: str,
    amount_cents: int,
    customer_name: str | None,
) -> str:
    """Template for payment approved message."""
    amount_formatted = f"R$ {amount_cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    customer_display = customer_name if customer_name else "Não informado"

    return (
        f"Pagamento confirmado\n\n"
        f"Pedido: {reference}\n"
        f"Valor: {amount_formatted}\n"
        f"Cliente: {customer_display}"
    )


def payment_failed_message(*, reference: str, amount_cents: int, failure_reason: str = "") -> str:
    """Template for payment attempt failed message."""
    amount_formatted = _brl(amount_cents)

    lines = [
        "Uma tentativa de pagamento não foi aprovada.",
        "",
        f"Pedido: {reference}",
        f"Valor: {amount_formatted}",
    ]

    if failure_reason:
        lines.append(f"Motivo: {failure_reason}")

    lines.extend([
        "",
        "O link continua disponível enquanto estiver ativo e o cliente pode tentar novamente.",
    ])

    return "\n".join(lines)


def payment_expired_message(*, reference: str) -> str:
    """Template for payment link expired message."""
    return (
        f"Link de pagamento expirado\n\n"
        f"Pedido: {reference}\n\n"
        f"O link não está mais disponível."
    )


def payment_canceled_message(*, reference: str) -> str:
    """Template for payment link canceled message."""
    return (
        f"Link de pagamento cancelado\n\n"
        f"Pedido: {reference}\n\n"
        f"O link foi cancelado."
    )


def payment_refunded_message(*, reference: str, amount_cents: int) -> str:
    """Template for payment link refunded message."""
    amount_formatted = f"R$ {amount_cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return (
        f"Pagamento estornado\n\n"
        f"Pedido: {reference}\n"
        f"Valor: {amount_formatted}\n\n"
        f"O pagamento foi estornado."
    )


def payment_chargedback_message(*, reference: str, amount_cents: int) -> str:
    """Template for payment link chargeback message."""
    amount_formatted = _brl(amount_cents)

    return (
        f"Chargeback recebido\n\n"
        f"Pedido: {reference}\n"
        f"Valor: {amount_formatted}\n\n"
        f"Um chargeback foi registrado para este pagamento. "
        f"Verifique a disputa no painel do Pagar.me."
    )


def boleto_created_seller_message(*, boleto) -> str:
    return (
        "Boleto emitido\n\n"
        f"Empresa: {boleto.company_snapshot['legal_name']}\n"
        f"CNPJ: {boleto.company_snapshot['cnpj']}\n"
        f"Valor: {_brl(boleto.amount_cents)}\n"
        f"Vencimento: {boleto.due_date:%d/%m/%Y}\n"
        "Status: Aguardando pagamento"
    )


def boleto_created_customer_message(*, boleto) -> str:
    lines = [
        f"Boleto emitido por {settings.APP_NAME}",
        "",
        f"Valor: {_brl(boleto.amount_cents)}",
        f"Vencimento: {boleto.due_date:%d/%m/%Y}",
        f"Linha digitável: {boleto.digitable_line}",
    ]
    if boleto.pdf_url:
        lines.extend(["", f"PDF: {boleto.pdf_url}"])
    return "\n".join(lines)


def boleto_status_message(*, boleto, event_type: str) -> str:
    headings = {
        "boleto_paid": "Pagamento de boleto confirmado",
        "boleto_failed": "Falha na cobrança do boleto",
        "boleto_canceled": "Boleto cancelado",
        "boleto_partially_canceled": "Boleto parcialmente cancelado",
        "boleto_expired": "Boleto vencido",
        "boleto_refunded": "Pagamento do boleto estornado",
    }
    lines = [
        headings[event_type],
        "",
        f"Empresa: {boleto.company_snapshot['legal_name']}",
        f"Valor: {_brl(boleto.amount_cents)}",
    ]
    if event_type == "boleto_paid" and boleto.paid_at:
        lines.append(f"Confirmado em: {boleto.paid_at:%d/%m/%Y %H:%M}")
    return "\n".join(lines)
