"""Payment links API — DRF views with seller session and API key auth."""
import contextlib

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.rate_limit import rate_limit
from apps.integrations.auth import authenticate_api_key

from .models import PaymentLink
from .use_cases import create_payment_link, format_currency


def _get_seller(request: Request):
    """Get seller from session or validate API key.

    Returns (seller, error_response) tuple.
    """
    # Try seller session first
    seller = getattr(request, "seller", None)
    if seller is not None:
        return seller, None

    # Try API key authentication
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        client = authenticate_api_key(auth_header)
        if client is not None:
            # API key auth — seller_id must be provided in query or body
            seller_id = request.query_params.get("seller_id") or request.data.get("seller_id")
            if seller_id:
                from apps.sellers.models import Seller

                try:
                    seller = Seller.objects.get(id=seller_id, is_active=True)
                    return seller, None
                except Seller.DoesNotExist:
                    pass
            # No seller_id — return error
            return None, Response(
                {"error": {"code": "missing_seller_id", "message": "seller_id é obrigatório para API Key."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

    return None, Response(
        {"error": {"code": "unauthorized", "message": "Autenticação inválida."}},
        status=status.HTTP_401_UNAUTHORIZED,
    )


@api_view(["POST"])
@rate_limit(max_requests=30, window_seconds=60)
def create_payment_link_view(request: Request) -> Response:
    """Create a new payment link.

    Requires seller session or API key authentication.
    Requires Idempotency-Key header.
    Rate limit: 30 requests per minute.
    """
    seller, error = _get_seller(request)
    if error:
        return error

    # Get idempotency key
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return Response(
            {"error": {"code": "missing_idempotency_key", "message": "Header Idempotency-Key é obrigatório."}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Parse request body
    data = request.data

    # Validate required fields
    reference = data.get("reference", "").strip()
    if not reference:
        return Response(
            {"error": {"code": "validation_error", "message": "Referência é obrigatória.", "field_errors": {"reference": ["Campo obrigatório."]}}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    amount_cents = data.get("amount_cents")
    if amount_cents is None:
        return Response(
            {"error": {"code": "validation_error", "message": "Valor é obrigatório.", "field_errors": {"amount_cents": ["Campo obrigatório."]}}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        amount_cents = int(amount_cents)
    except (TypeError, ValueError):
        return Response(
            {"error": {"code": "validation_error", "message": "Valor inválido.", "field_errors": {"amount_cents": ["Deve ser um número inteiro."]}}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    installments = data.get("installments", 1)
    try:
        installments = int(installments)
    except (TypeError, ValueError):
        installments = 1

    # Optional fields
    customer_name = data.get("customer_name") or None
    customer_phone = data.get("customer_phone") or None
    description = data.get("description") or None
    expires_in_minutes = data.get("expires_in_minutes")

    if expires_in_minutes is not None:
        try:
            expires_in_minutes = int(expires_in_minutes)
            if expires_in_minutes < 10 or expires_in_minutes > 43200:
                expires_in_minutes = None
        except (TypeError, ValueError):
            expires_in_minutes = None

    # Execute use case
    result = create_payment_link(
        seller=seller,
        reference=reference,
        amount_cents=amount_cents,
        installments=installments,
        idempotency_key=idempotency_key,
        customer_name=customer_name,
        customer_phone=customer_phone,
        description=description,
        expires_in_minutes=expires_in_minutes,
    )

    if not result.success:
        # Check for idempotency conflict
        if "diferentes" in result.error_message:
            return Response(
                {"error": {"code": "idempotency_conflict", "message": result.error_message}},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {"error": {"code": "validation_error", "message": result.error_message}},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Build response
    link = result.payment_link
    response_data = {
        "data": {
            "id": str(link.id),
            "reference": link.reference,
            "amount_cents": link.amount_cents,
            "amount_formatted": format_currency(link.amount_cents),
            "installments": link.installments,
            "status": link.status,
            "payment_url": link.payment_url or None,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "whatsapp_delivery": {
                "status": "QUEUED" if link.status == "ACTIVE" else "PENDING",
            },
            "created_at": link.created_at.isoformat(),
        }
    }

    if result.uncertain:
        return Response(response_data, status=status.HTTP_202_ACCEPTED)

    return Response(response_data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def list_payment_links_view(request: Request) -> Response:
    """List payment links with cursor pagination and filters.

    Query params:
        status: filter by status
        cursor: pagination cursor (UUID of last item)
        limit: number of items (default 20, max 100)
        seller_id: required for API key auth
    """
    seller, error = _get_seller(request)
    if error:
        return error

    # Parse filters
    status_filter = request.query_params.get("status", "")
    cursor = request.query_params.get("cursor", "")
    limit = min(int(request.query_params.get("limit", 20)), 100)

    # Build query
    links = PaymentLink.objects.filter(seller=seller)

    if status_filter:
        links = links.filter(status=status_filter)

    # Cursor pagination
    if cursor:
        with contextlib.suppress(Exception):
            links = links.filter(created_at__lt=cursor)

    links = links.order_by("-created_at")[: limit + 1]

    # Check if there are more items
    has_next = len(links) > limit
    links = links[:limit]

    data = [
        {
            "id": str(link.id),
            "reference": link.reference,
            "customer_name": link.customer_name or None,
            "amount_cents": link.amount_cents,
            "installments": link.installments,
            "status": link.status,
            "last_attempt_status": _get_last_attempt_status(link),
            "created_at": link.created_at.isoformat(),
        }
        for link in links
    ]

    next_cursor = data[-1]["created_at"] if has_next and data else None

    return Response({
        "data": data,
        "pagination": {
            "next_cursor": next_cursor,
            "has_next": has_next,
        },
    })


@api_view(["GET"])
def get_payment_link_view(request: Request, link_id: str) -> Response:
    """Get payment link details with attempts and timeline."""
    seller, error = _get_seller(request)
    if error:
        return error

    try:
        link = PaymentLink.objects.get(id=link_id, seller=seller)
    except PaymentLink.DoesNotExist:
        return Response(
            {"error": {"code": "not_found", "message": "Link não encontrado."}},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Get attempts
    attempts = link.attempts.order_by("-created_at")
    attempts_data = [
        {
            "id": str(attempt.id),
            "provider_order_id": attempt.provider_order_id,
            "provider_charge_id": attempt.provider_charge_id,
            "status": attempt.status,
            "amount_cents": attempt.amount_cents,
            "installments": attempt.installments,
            "failure_code": attempt.failure_code or None,
            "failure_message": attempt.failure_message or None,
            "paid_at": attempt.paid_at.isoformat() if attempt.paid_at else None,
            "created_at": attempt.created_at.isoformat(),
        }
        for attempt in attempts
    ]

    # Build timeline
    timeline = _build_timeline(link, attempts)

    data = {
        "id": str(link.id),
        "reference": link.reference,
        "customer_name": link.customer_name or None,
        "customer_phone": link.customer_phone or None,
        "description": link.description or None,
        "amount_cents": link.amount_cents,
        "amount_formatted": format_currency(link.amount_cents),
        "installments": link.installments,
        "status": link.status,
        "payment_url": link.payment_url or None,
        "provider_link_id": link.provider_link_id or None,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "paid_at": link.paid_at.isoformat() if link.paid_at else None,
        "canceled_at": link.canceled_at.isoformat() if link.canceled_at else None,
        "refunded_at": link.refunded_at.isoformat() if link.refunded_at else None,
        "created_at": link.created_at.isoformat(),
        "updated_at": link.updated_at.isoformat(),
        "attempts": attempts_data,
        "timeline": timeline,
    }

    return Response({"data": data})


@api_view(["POST"])
def resend_payment_link_view(request: Request, link_id: str) -> Response:
    """Resend payment link via WhatsApp."""
    seller, error = _get_seller(request)
    if error:
        return error

    # Get idempotency key
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return Response(
            {"error": {"code": "missing_idempotency_key", "message": "Header Idempotency-Key é obrigatório."}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        link = PaymentLink.objects.get(id=link_id, seller=seller)
    except PaymentLink.DoesNotExist:
        return Response(
            {"error": {"code": "not_found", "message": "Link não encontrado."}},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not link.payment_url:
        return Response(
            {"error": {"code": "no_url", "message": "Link não possui URL para enviar."}},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Queue WhatsApp message
    from apps.notifications.whatsapp_service import queue_payment_link_created

    message = queue_payment_link_created(seller=seller, payment_link=link)

    return Response(
        {
            "data": {
                "message_id": str(message.id),
                "status": "QUEUED",
            }
        },
        status=status.HTTP_202_ACCEPTED,
    )


def _get_last_attempt_status(link) -> str | None:
    """Get the status of the last payment attempt."""
    last_attempt = link.attempts.order_by("-created_at").first()
    return last_attempt.status if last_attempt else None


def _build_timeline(link, attempts):
    """Build a sanitized timeline of events."""
    timeline = []

    # Link created
    timeline.append({
        "event": "link_created",
        "timestamp": link.created_at.isoformat(),
        "details": f"Link criado com valor {format_currency(link.amount_cents)}",
    })

    # Status changes
    if link.status == "ACTIVE":
        timeline.append({
            "event": "link_activated",
            "timestamp": link.created_at.isoformat(),
            "details": "Link ativo e pronto para uso",
        })

    if link.paid_at:
        timeline.append({
            "event": "payment_confirmed",
            "timestamp": link.paid_at.isoformat(),
            "details": "Pagamento confirmado",
        })

    if link.canceled_at:
        timeline.append({
            "event": "link_canceled",
            "timestamp": link.canceled_at.isoformat(),
            "details": "Link cancelado",
        })

    if link.refunded_at:
        timeline.append({
            "event": "payment_refunded",
            "timestamp": link.refunded_at.isoformat(),
            "details": "Pagamento estornado",
        })

    # Attempts
    for attempt in attempts:
        timeline.append({
            "event": f"attempt_{attempt.status.lower()}",
            "timestamp": attempt.created_at.isoformat(),
            "details": f"Tentativa {attempt.status}",
        })

    # Sort by timestamp
    timeline.sort(key=lambda x: x["timestamp"])

    return timeline
