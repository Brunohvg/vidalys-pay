"""Authenticated API endpoints for the complete boleto lifecycle."""
import hashlib

from django.core.exceptions import ValidationError
from django.views.decorators.http import require_http_methods
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.boletos.gateways.cnpj_provider import (
    CnpjNotFoundError,
    CnpjProviderTimeoutError,
    CnpjProviderUnavailableError,
)
from apps.boletos.models import Boleto, BoletoStatus
from apps.boletos.serializers import (
    BoletoCreateSerializer,
    BoletoListQuerySerializer,
    BoletoSecondCopySerializer,
)
from apps.boletos.services.boleto_cancellation import cancel_boleto
from apps.boletos.services.boleto_creation import (
    BoletoCreationData,
    create_boleto,
)
from apps.boletos.services.cnpj_lookup import lookup_company
from apps.core.rate_limit import rate_limit
from apps.integrations.auth import authenticate_api_key, has_scope


@require_http_methods(["GET", "POST"])
def boletos_collection_view(request):
    handler = list_boletos_view if request.method == "GET" else create_boleto_view
    return handler(request)


def _get_seller(request, *, required_scope: str):
    seller = getattr(request, "seller", None)
    if seller is None:
        seller = getattr(getattr(request, "_request", None), "seller", None)
    if seller is not None and seller.is_active:
        return seller, None

    client = authenticate_api_key(request.META.get("HTTP_AUTHORIZATION", ""))
    if client is not None:
        if not has_scope(client, required_scope):
            return None, Response(
                {"error": {"code": "insufficient_scope", "message": "A chave não possui permissão para esta operação."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        seller_id = request.query_params.get("seller_id")
        if request.method in {"POST", "PUT", "PATCH"}:
            seller_id = seller_id or request.data.get("seller_id")
        if seller_id:
            from apps.sellers.models import Seller

            seller = Seller.objects.filter(id=seller_id, is_active=True).first()
            if seller:
                return seller, None
        return None, Response(
            {"error": {"code": "missing_seller_id", "message": "seller_id válido é obrigatório para API Key."}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return None, Response(
        {"error": {"code": "seller_not_authenticated", "message": "Sua sessão expirou. Entre novamente."}},
        status=status.HTTP_401_UNAUTHORIZED,
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@rate_limit(max_requests=20, window_seconds=60)
def create_boleto_view(request) -> Response:
    seller, error = _get_seller(request, required_scope="boletos:write")
    if error:
        return error
    idempotency_key, error = _idempotency_key(request)
    if error:
        return error
    serializer = BoletoCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return _validation_error(serializer.errors)
    data = serializer.validated_data
    result = create_boleto(
        seller=seller,
        actor_seller=seller,
        data=BoletoCreationData(
            cnpj=data["cnpj"],
            legal_name=data["legal_name"],
            trade_name=data["trade_name"],
            email=data["email"],
            phone=data["phone"],
            whatsapp_phone=data["whatsapp_phone"],
            zip_code=data["zip_code"],
            street=data["street"],
            number=data["number"],
            complement=data["complement"],
            district=data["district"],
            city=data["city"],
            state=data["state"],
            amount_cents=data["amount_cents"],
            due_date=data["due_date"],
            description=data["description"],
            internal_reference=data["internal_reference"],
            internal_notes=data["internal_notes"],
        ),
        idempotency_key=idempotency_key,
    )
    if not result.boleto:
        code = "idempotency_conflict" if "dados diferentes" in result.error_message else "business_rule"
        http_status = status.HTTP_409_CONFLICT if code == "idempotency_conflict" else status.HTTP_422_UNPROCESSABLE_ENTITY
        return Response(
            {"error": {"code": code, "message": result.error_message}},
            status=http_status,
        )
    if not result.success and not result.uncertain:
        return Response(
            {
                "error": {
                    "code": "provider_rejected",
                    "message": result.error_message,
                    "boleto_id": str(result.boleto.id),
                }
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    response_status = status.HTTP_202_ACCEPTED if result.uncertain else status.HTTP_201_CREATED
    return Response(
        {"data": _serialize_boleto(result.boleto, detailed=True)},
        status=response_status,
    )


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def list_boletos_view(request) -> Response:
    seller, error = _get_seller(request, required_scope="boletos:read")
    if error:
        return error
    serializer = BoletoListQuerySerializer(data=request.query_params)
    if not serializer.is_valid():
        return _validation_error(serializer.errors)
    filters = serializer.validated_data
    queryset = Boleto.objects.filter(seller=seller).select_related("company", "seller")
    if filters["status"]:
        queryset = queryset.filter(status=filters["status"])
    if filters["cursor"]:
        queryset = queryset.filter(created_at__lt=filters["cursor"])
    if filters["due_from"]:
        queryset = queryset.filter(due_date__gte=filters["due_from"])
    if filters["due_to"]:
        queryset = queryset.filter(due_date__lte=filters["due_to"])
    limit = filters["limit"]
    boletos = list(queryset.order_by("-created_at")[: limit + 1])
    has_next = len(boletos) > limit
    boletos = boletos[:limit]
    return Response(
        {
            "data": [_serialize_boleto(boleto) for boleto in boletos],
            "pagination": {
                "next_cursor": boletos[-1].created_at.isoformat() if has_next and boletos else None,
                "has_next": has_next,
            },
        }
    )


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def get_boleto_view(request, boleto_id) -> Response:
    boleto, error = _scoped_boleto(request, boleto_id, scope="boletos:read")
    if error:
        return error
    return Response({"data": _serialize_boleto(boleto, detailed=True)})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def get_boleto_status_view(request, boleto_id) -> Response:
    boleto, error = _scoped_boleto(request, boleto_id, scope="boletos:read")
    if error:
        return error
    return Response(
        {
            "data": {
                "id": str(boleto.id),
                "status": boleto.status,
                "provider_status": boleto.provider_status or None,
                "due_date": boleto.due_date.isoformat(),
                "paid_at": _iso(boleto.paid_at),
                "canceled_at": _iso(boleto.canceled_at),
                "refunded_at": _iso(boleto.refunded_at),
                "updated_at": boleto.updated_at.isoformat(),
            }
        }
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@rate_limit(max_requests=10, window_seconds=60)
def cancel_boleto_view(request, boleto_id) -> Response:
    boleto, error = _scoped_boleto(request, boleto_id, scope="boletos:write")
    if error:
        return error
    idempotency_key, error = _idempotency_key(request)
    if error:
        return error
    result = cancel_boleto(
        boleto=boleto,
        idempotency_key=idempotency_key,
    )
    if not result.success:
        code = "cancellation_in_progress" if "processamento" in result.error_message else "not_cancelable"
        http_status = status.HTTP_409_CONFLICT if code == "cancellation_in_progress" else status.HTTP_422_UNPROCESSABLE_ENTITY
        return Response(
            {"error": {"code": code, "message": result.error_message}},
            status=http_status,
        )
    return Response(
        {"data": _serialize_boleto(result.boleto, detailed=True)},
        status=status.HTTP_202_ACCEPTED if result.uncertain else status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@rate_limit(max_requests=20, window_seconds=60)
def resend_boleto_view(request, boleto_id) -> Response:
    boleto, error = _scoped_boleto(request, boleto_id, scope="notifications:write")
    if error:
        return error
    idempotency_key, error = _idempotency_key(request)
    if error:
        return error
    if not boleto.digitable_line and not boleto.pdf_url:
        return Response(
            {"error": {"code": "boleto_not_ready", "message": "Boleto ainda não possui dados para reenvio."}},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    from apps.notifications.whatsapp_service import queue_boleto_created

    suffix = hashlib.sha256(idempotency_key.encode()).hexdigest()[:24]
    deliveries = queue_boleto_created(
        boleto=boleto,
        deduplication_suffix=f"resend:{suffix}",
    )
    return Response(
        {
            "data": {
                "deliveries": [
                    {
                        "recipient_type": delivery.recipient_type,
                        "status": delivery.status,
                    }
                    for delivery in deliveries
                ]
            }
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@rate_limit(max_requests=10, window_seconds=60)
def create_second_copy_view(request, boleto_id) -> Response:
    original, error = _scoped_boleto(request, boleto_id, scope="boletos:write")
    if error:
        return error
    idempotency_key, error = _idempotency_key(request)
    if error:
        return error
    serializer = BoletoSecondCopySerializer(data=request.data)
    if not serializer.is_valid():
        return _validation_error(serializer.errors)
    if original.status not in {
        BoletoStatus.CANCELED,
        BoletoStatus.EXPIRED,
        BoletoStatus.FAILED,
    }:
        return Response(
            {
                "error": {
                    "code": "original_not_closed",
                    "message": "Cancele ou encerre o boleto original antes de emitir a segunda via.",
                }
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    snapshot = original.company_snapshot
    address = snapshot.get("address") or {}
    result = create_boleto(
        seller=original.seller,
        actor_seller=original.seller,
        data=BoletoCreationData(
            cnpj=snapshot.get("cnpj", ""),
            legal_name=snapshot.get("legal_name", ""),
            trade_name=snapshot.get("trade_name", ""),
            email=snapshot.get("email", ""),
            phone=snapshot.get("phone", ""),
            whatsapp_phone=snapshot.get("whatsapp_phone", ""),
            zip_code=address.get("zip_code", ""),
            street=address.get("street", ""),
            number=address.get("number", ""),
            complement=address.get("complement", ""),
            district=address.get("district", ""),
            city=address.get("city", ""),
            state=address.get("state", ""),
            amount_cents=original.amount_cents,
            due_date=serializer.validated_data["due_date"],
            description=original.description,
            internal_reference=original.internal_reference,
            internal_notes=original.internal_notes,
        ),
        idempotency_key=idempotency_key,
        reissued_from=original,
    )
    if not result.boleto:
        code = (
            "idempotency_conflict"
            if "dados diferentes" in result.error_message
            else "business_rule"
        )
        return Response(
            {"error": {"code": code, "message": result.error_message}},
            status=(
                status.HTTP_409_CONFLICT
                if code == "idempotency_conflict"
                else status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
        )
    return Response(
        {"data": _serialize_boleto(result.boleto, detailed=True)},
        status=(
            status.HTTP_202_ACCEPTED
            if result.uncertain
            else status.HTTP_201_CREATED
        ),
    )


def _scoped_boleto(request, boleto_id, *, scope):
    seller, error = _get_seller(request, required_scope=scope)
    if error:
        return None, error
    boleto = (
        Boleto.objects.filter(id=boleto_id, seller=seller)
        .select_related("company", "seller")
        .first()
    )
    if not boleto:
        return None, Response(
            {"error": {"code": "not_found", "message": "Boleto não encontrado."}},
            status=status.HTTP_404_NOT_FOUND,
        )
    return boleto, None


def _idempotency_key(request):
    key = request.headers.get("Idempotency-Key", "")
    if not key:
        return None, Response(
            {"error": {"code": "missing_idempotency_key", "message": "Header Idempotency-Key é obrigatório."}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(key) > 100:
        return None, Response(
            {"error": {"code": "validation_error", "message": "Idempotency-Key deve ter no máximo 100 caracteres."}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return key, None


def _serialize_boleto(boleto, *, detailed=False):
    data = {
        "id": str(boleto.id),
        "internal_reference": boleto.internal_reference or None,
        "company": {
            "cnpj": boleto.company_snapshot.get("cnpj"),
            "legal_name": boleto.company_snapshot.get("legal_name"),
            "trade_name": boleto.company_snapshot.get("trade_name") or None,
        },
        "amount_cents": boleto.amount_cents,
        "due_date": boleto.due_date.isoformat(),
        "description": boleto.description,
        "status": boleto.status,
        "created_at": boleto.created_at.isoformat(),
        "updated_at": boleto.updated_at.isoformat(),
        "reissued_from_id": (
            str(boleto.reissued_from_id) if boleto.reissued_from_id else None
        ),
        "reissue_ids": [
            str(value) for value in boleto.reissues.values_list("id", flat=True)
        ],
    }
    if detailed:
        data.update(
            {
                "digitable_line": boleto.digitable_line or None,
                "barcode": boleto.barcode or None,
                "pdf_url": boleto.pdf_url or None,
                "provider_order_id": boleto.provider_order_id,
                "provider_charge_id": boleto.provider_charge_id,
                "provider_status": boleto.provider_status or None,
                "paid_at": _iso(boleto.paid_at),
                "failed_at": _iso(boleto.failed_at),
                "expired_at": _iso(boleto.expired_at),
                "canceled_at": _iso(boleto.canceled_at),
                "refunded_at": _iso(boleto.refunded_at),
                "notifications": [
                    {
                        "channel": "whatsapp",
                        "recipient_type": message.recipient_type,
                        "event_type": message.event_type,
                        "status": message.status,
                        "created_at": message.created_at.isoformat(),
                    }
                    for message in boleto.whatsapp_messages.order_by("-created_at")[:50]
                ],
            }
        )
    return data


def _iso(value):
    return value.isoformat() if value else None


def _validation_error(errors):
    return Response(
        {
            "error": {
                "code": "validation_error",
                "message": "Revise os campos informados.",
                "field_errors": _stringify_errors(errors),
            }
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _stringify_errors(value):
    if isinstance(value, dict):
        return {key: _stringify_errors(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stringify_errors(item) for item in value]
    return str(value)


def _has_boleto_access(request) -> bool:
    seller = getattr(request, "seller", None)
    if seller is not None and seller.is_active:
        return True
    django_request = getattr(request, "_request", request)
    user = getattr(django_request, "user", None)
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_superuser", False)
    )


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
@rate_limit(max_requests=20, window_seconds=60)
def lookup_cnpj_view(request, cnpj: str) -> Response:
    """Look up one validated company CNPJ without persisting provider data."""
    if not _has_boleto_access(request):
        return Response(
            {
                "error": {
                    "code": "not_authenticated",
                    "message": "Autenticação necessária para consultar CNPJ.",
                }
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        result = lookup_company(cnpj)
    except ValidationError as exc:
        return Response(
            {"error": {"code": "invalid_cnpj", "message": exc.messages[0]}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except CnpjNotFoundError:
        return Response(
            {"error": {"code": "not_found", "message": "CNPJ não encontrado."}},
            status=status.HTTP_404_NOT_FOUND,
        )
    except CnpjProviderTimeoutError:
        return Response(
            {
                "error": {
                    "code": "provider_timeout",
                    "message": "A consulta demorou mais que o esperado. Tente novamente.",
                }
            },
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    except CnpjProviderUnavailableError:
        return Response(
            {
                "error": {
                    "code": "provider_unavailable",
                    "message": "A consulta de CNPJ está temporariamente indisponível.",
                }
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"data": result.as_dict()}, status=status.HTTP_200_OK)
