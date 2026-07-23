"""Payment links API — DRF views with seller session and API key auth."""
import hashlib
import logging

from django.views.decorators.http import require_http_methods
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.rate_limit import rate_limit
from apps.integrations.auth import authenticate_api_key, has_scope

from .models import PaymentLink
from .serializers import PaymentLinkCreateSerializer, PaymentLinkListQuerySerializer
from .use_cases import create_payment_link, format_currency

logger = logging.getLogger("apps.payment_links")


@require_http_methods(["GET", "POST"])
def payment_links_collection_view(request):
    """Route collection reads and creates to their DRF handlers."""
    handler = list_payment_links_view if request.method == "GET" else create_payment_link_view
    return handler(request)


def _get_seller(request: Request, *, required_scope: str | None = None):
    """Get seller from session or validate API key.

    Returns (seller, error_response) tuple.
    """
    # Try seller session first
    seller = getattr(request, "seller", None)
    if seller is None:
        # Try underlying Django HttpRequest (DRF Request wraps it)
        inner = getattr(request, "_request", None)
        if inner is not None:
            seller = getattr(inner, "seller", None)
    if seller is not None:
        return seller, None

    # Try API key authentication
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        client = authenticate_api_key(auth_header)
        if client is not None:
            if required_scope and not has_scope(client, required_scope):
                return None, Response(
                    {"error": {"code": "insufficient_scope", "message": "A chave não possui permissão para esta operação."}},
                    status=status.HTTP_403_FORBIDDEN,
                )
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
        {"error": {"code": "seller_not_authenticated", "message": "Sua sessão expirou. Entre novamente."}},
        status=status.HTTP_401_UNAUTHORIZED,
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@rate_limit(max_requests=30, window_seconds=60)
def create_payment_link_view(request: Request) -> Response:
    """Create a new payment link.

    Requires seller session or API key authentication.
    Requires Idempotency-Key header.
    Rate limit: 30 requests per minute.
    """
    seller, error = _get_seller(request, required_scope="payment_links:write")
    if error:
        return error

    logger.info(
        "seller_authenticated=true seller_id=%s pagarme_call_started=false",
        seller.id,
    )

    # Get idempotency key
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return Response(
            {"error": {"code": "missing_idempotency_key", "message": "Header Idempotency-Key é obrigatório."}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(idempotency_key) > 100:
        return Response(
            {"error": {"code": "validation_error", "message": "Idempotency-Key deve ter no máximo 100 caracteres."}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = PaymentLinkCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return _validation_error(serializer.errors)
    validated = serializer.validated_data

    logger.info(
        "seller_authenticated=true seller_id=%s pagarme_call_started=true",
        seller.id,
    )

    # Execute use case
    result = create_payment_link(
        seller=seller,
        reference=validated["reference"],
        amount_cents=validated["amount_cents"],
        installments=validated["installments"],
        idempotency_key=idempotency_key,
        customer_name=validated["customer_name"] or None,
        customer_phone=validated["customer_phone"] or None,
        description=validated["description"] or None,
        expires_in_minutes=validated["expires_in_minutes"],
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

    # Queue WhatsApp notifications (seller + optional customer)
    whatsapp_status = _queue_whatsapp_notifications(seller=seller, payment_link=link)

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
            "whatsapp": whatsapp_status,
            "created_at": link.created_at.isoformat(),
        }
    }

    if result.uncertain:
        return Response(response_data, status=status.HTTP_202_ACCEPTED)

    return Response(response_data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def list_payment_links_view(request: Request) -> Response:
    """List payment links with cursor pagination and filters.

    Query params:
        status: filter by status
        cursor: pagination cursor (UUID of last item)
        limit: number of items (default 20, max 100)
        seller_id: required for API key auth
    """
    seller, error = _get_seller(request, required_scope="payment_links:read")
    if error:
        return error

    serializer = PaymentLinkListQuerySerializer(data=request.query_params)
    if not serializer.is_valid():
        return _validation_error(serializer.errors)
    filters = serializer.validated_data
    status_filter = filters["status"]
    cursor = filters["cursor"]
    limit = filters["limit"]

    # Build query
    links = PaymentLink.objects.filter(seller=seller)

    if status_filter:
        links = links.filter(status=status_filter)

    # Cursor pagination
    if cursor:
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
@authentication_classes([])
@permission_classes([AllowAny])
def get_payment_link_view(request: Request, link_id: str) -> Response:
    """Get payment link details with attempts and timeline."""
    seller, error = _get_seller(request, required_scope="payment_links:read")
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

    # Get WhatsApp messages for this link

    whatsapp_messages = link.whatsapp_messages.order_by("created_at")
    whatsapp_data = [
        {
            "id": str(msg.id),
            "recipient_type": msg.recipient_type,
            "recipient_phone": msg.recipient_phone,
            "status": msg.status,
            "event_type": msg.event_type,
            "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
        }
        for msg in whatsapp_messages
    ]

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
        "whatsapp_messages": whatsapp_data,
    }

    return Response({"data": data})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def resend_payment_link_view(request: Request, link_id: str) -> Response:
    """Resend payment link via WhatsApp."""
    seller, error = _get_seller(request, required_scope="notifications:write")
    if error:
        return error

    # Get idempotency key
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return Response(
            {"error": {"code": "missing_idempotency_key", "message": "Header Idempotency-Key é obrigatório."}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(idempotency_key) > 100:
        return Response(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Idempotency-Key deve ter no máximo 100 caracteres.",
                }
            },
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

    # Queue WhatsApp notifications (seller + optional customer)
    deduplication_suffix = hashlib.sha256(idempotency_key.encode()).hexdigest()[:24]
    whatsapp_status = _queue_whatsapp_notifications(
        seller=seller,
        payment_link=link,
        deduplication_suffix=f"resend:{deduplication_suffix}",
        deduplicate_forever=True,
    )

    return Response(
        {
            "data": {
                "whatsapp": whatsapp_status,
            }
        },
        status=status.HTTP_202_ACCEPTED,
    )


def _queue_whatsapp_notifications(
    *,
    seller,
    payment_link,
    deduplication_suffix: str = "",
    deduplicate_forever: bool = False,
) -> dict:
    """Queue WhatsApp notifications for seller and optionally customer.

    Returns a dict with separate statuses for each recipient.
    """
    from apps.notifications.whatsapp_service import queue_payment_link_created

    results = queue_payment_link_created(
        seller=seller,
        payment_link=payment_link,
        deduplication_suffix=deduplication_suffix,
        deduplicate_forever=deduplicate_forever,
    )

    whatsapp = {}
    for result in results:
        whatsapp[result.recipient_type] = {
            "status": result.status,
            "message": _whatsapp_status_message(result),
        }

    return whatsapp


def _whatsapp_status_message(result) -> str:
    """Return a user-friendly message for the WhatsApp delivery status."""
    if result.recipient_type == "seller":
        if result.status == "queued":
            return "Envio para seu WhatsApp agendado."
        elif result.status == "duplicate":
            return "Envio para seu WhatsApp já está na fila."
        elif result.status == "failed":
            return "Não foi possível agendar envio para seu WhatsApp."
    elif result.recipient_type == "customer":
        if result.status == "queued":
            return "Envio para o cliente agendado."
        elif result.status == "duplicate":
            return "Envio para o cliente já está na fila."
        elif result.status == "not_requested":
            return "Cliente sem telefone informado."
    return ""


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


def _validation_error(errors) -> Response:
    field_errors = {
        field: [str(message) for message in messages]
        for field, messages in errors.items()
    }
    return Response(
        {
            "error": {
                "code": "validation_error",
                "message": "Revise os campos informados.",
                "field_errors": field_errors,
            }
        },
        status=status.HTTP_400_BAD_REQUEST,
    )
