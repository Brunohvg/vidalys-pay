"""Authenticated API endpoints for boleto support workflows."""
from django.core.exceptions import ValidationError
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
from apps.boletos.services.cnpj_lookup import lookup_company
from apps.core.rate_limit import rate_limit


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
