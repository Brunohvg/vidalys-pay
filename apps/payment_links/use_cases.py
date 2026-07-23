"""Payment link use cases — business logic for creating and managing links."""
import logging

from django.utils import timezone

from apps.integrations.pagarme.client import PagarmeClient, PagarmeError
from apps.sellers.models import Seller

from .models import PaymentLink, PaymentLinkStatus

logger = logging.getLogger("apps.payment_links")


class CreatePaymentLinkResult:
    """Result of creating a payment link."""

    def __init__(
        self,
        payment_link: PaymentLink,
        *,
        success: bool = True,
        error_message: str = "",
        uncertain: bool = False,
    ):
        self.payment_link = payment_link
        self.success = success
        self.error_message = error_message
        self.uncertain = uncertain


def create_payment_link(
    *,
    seller: Seller,
    reference: str,
    amount_cents: int,
    installments: int,
    idempotency_key: str,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    description: str | None = None,
    expires_in_minutes: int | None = None,
) -> CreatePaymentLinkResult:
    """Create a payment link for a seller.

    Steps:
    1. Validate seller and limits
    2. Check idempotency
    3. Create local record in CREATING state
    4. Call Pagar.me API
    5. Update record with response
    6. Return result
    """
    # Validate seller
    if not seller.is_active:
        return CreatePaymentLinkResult(
            payment_link=None,
            success=False,
            error_message="Vendedor inativo.",
        )

    if not reference or len(reference) > 80 or not idempotency_key or len(idempotency_key) > 100:
        return CreatePaymentLinkResult(
            payment_link=None,
            success=False,
            error_message="Referência ou chave de idempotência inválida.",
        )

    for value, max_length in ((customer_name, 120), (customer_phone, 20), (description, 255)):
        if value is not None and (not isinstance(value, str) or len(value) > max_length):
            return CreatePaymentLinkResult(
                payment_link=None,
                success=False,
                error_message="Dados do cliente excedem o tamanho permitido.",
            )

    # Validate amount
    if amount_cents <= 0:
        return CreatePaymentLinkResult(
            payment_link=None,
            success=False,
            error_message="Valor deve ser maior que zero.",
        )

    if amount_cents > seller.max_payment_amount_cents:
        return CreatePaymentLinkResult(
            payment_link=None,
            success=False,
            error_message=f"Valor máximo para este vendedor: R$ {seller.max_payment_amount_cents / 100:.2f}.",
        )

    # Validate installments
    if installments not in (1, 2, 3):
        return CreatePaymentLinkResult(
            payment_link=None,
            success=False,
            error_message="Parcelamento deve ser 1x, 2x ou 3x.",
        )

    # Check idempotency
    existing = PaymentLink.objects.filter(
        seller=seller,
        idempotency_key=idempotency_key,
    ).first()

    if existing:
        # Same key, same payload = return existing
        if (
            existing.amount_cents == amount_cents
            and existing.installments == installments
            and existing.reference == reference
        ):
            logger.info("Idempotência: reutilizando link existente %s", existing.id)
            return CreatePaymentLinkResult(payment_link=existing)

        # Different payload = conflict
        return CreatePaymentLinkResult(
            payment_link=None,
            success=False,
            error_message="Chave de idempotência reutilizada com dados diferentes.",
        )

    # Create local record
    payment_link = PaymentLink.objects.create(
        seller=seller,
        reference=reference,
        customer_name=customer_name or "",
        customer_phone=customer_phone or "",
        description=description or "",
        amount_cents=amount_cents,
        installments=installments,
        status=PaymentLinkStatus.CREATING,
        idempotency_key=idempotency_key,
        creation_request={
            "reference": reference,
            "amount_cents": amount_cents,
            "installments": installments,
        },
    )

    # Call Pagar.me
    try:
        client = PagarmeClient()
        response = client.create_payment_link(
            name=f"Pedido {reference}"[:64],
            reference=reference,
            amount_cents=amount_cents,
            installments=installments,
            max_paid_sessions=1,
            expires_in_minutes=expires_in_minutes,
            customer_name=customer_name,
            metadata={
                "internal_payment_link_id": str(payment_link.id),
                "seller_id": str(seller.id),
                "reference": reference,
            },
        )

        # Update with response
        payment_link.provider_link_id = response.get("id", "")
        payment_link.payment_url = response.get("url", "")
        payment_link.provider_status = response.get("status", "")
        payment_link.creation_response = response

        # Map status
        status = response.get("status", "")
        if status == "active":
            payment_link.status = PaymentLinkStatus.ACTIVE
        elif status == "building":
            payment_link.status = PaymentLinkStatus.CREATING
        else:
            payment_link.status = PaymentLinkStatus.ACTIVE

        # Set expiration if provided
        if expires_in_minutes and not payment_link.expires_at:
            payment_link.expires_at = timezone.now() + timezone.timedelta(minutes=expires_in_minutes)

        payment_link.save()

        logger.info(
            "Link criado com sucesso: id=%s provider_id=%s status=%s",
            payment_link.id,
            payment_link.provider_link_id,
            payment_link.status,
        )

        return CreatePaymentLinkResult(payment_link=payment_link)

    except PagarmeError as e:
        # Definitive error
        payment_link.status = PaymentLinkStatus.CREATION_ERROR
        payment_link.creation_response = {"error": e.error_data}
        payment_link.save()

        logger.error(
            "Erro definitivo ao criar link: id=%s error=%s",
            payment_link.id,
            e.error_data,
        )

        return CreatePaymentLinkResult(
            payment_link=payment_link,
            success=False,
            error_message="Não foi possível criar o link. Nenhuma cobrança foi confirmada. Tente novamente.",
        )

    except Exception as e:
        # Timeout or uncertain result
        payment_link.status = PaymentLinkStatus.CREATION_UNKNOWN
        payment_link.creation_response = {"error": str(e)}
        payment_link.save()

        logger.exception(
            "Resultado incerto ao criar link: id=%s",
            payment_link.id,
        )

        return CreatePaymentLinkResult(
            payment_link=payment_link,
            success=True,
            uncertain=True,
            error_message="Estamos confirmando se o link foi criado. Não tente novamente até a atualização desta tela.",
        )


def format_currency(cents: int) -> str:
    """Format cents to BRL currency string."""
    return f"R$ {cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
