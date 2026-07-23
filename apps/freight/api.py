"""Freight API endpoints."""
import logging
import re

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.rate_limit import rate_limit
from apps.sellers.decorators import seller_login_required

from .exceptions import (
    FreightConfigurationError,
    FreightProviderUnavailable,
    FreightValidationError,
)
from .services import (
    calculate_freight,
    format_price_cents,
    lookup_cep,
    validate_and_build_package,
)

logger = logging.getLogger("apps.freight")


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@rate_limit(max_requests=30, window_seconds=60)
@seller_login_required
def lookup_cep_view(request: Request) -> Response:
    """Look up CEP address via ViaCEP with BrasilAPI fallback.

    POST /api/v1/freight/cep/
    Body: {"zip_code": "30140071"}
    """
    data = request.data
    zip_code = re.sub(r"\D", "", str(data.get("zip_code") or ""))

    if len(zip_code) != 8:
        return Response(
            {"error": {"code": "invalid_zip", "message": "Informe um CEP válido com oito números."}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = lookup_cep(zip_code)

    if result is None:
        return Response(
            {"error": {"code": "not_found", "message": "CEP não encontrado."}},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        "data": {
            "zip_code": f"{result.zip_code[:5]}-{result.zip_code[5:]}",
            "street": result.street,
            "neighborhood": result.neighborhood,
            "city": result.city,
            "state": result.state,
            "source": result.source,
        }
    }, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@rate_limit(max_requests=20, window_seconds=60)
@seller_login_required
def calculate_freight_view(request: Request) -> Response:
    """Calculate freight for PAC and SEDEX.

    POST /api/v1/freight/calculate/
    """
    data = request.data
    seller = request.seller

    destination_zip_code = re.sub(r"\D", "", str(data.get("destination_zip_code") or ""))
    weight_grams = data.get("weight_grams", 0)
    length_cm = data.get("length_cm", 0)
    width_cm = data.get("width_cm", 0)
    height_cm = data.get("height_cm", 0)
    declared_value_cents = data.get("declared_value_cents", 0)

    # Validate CEP first
    if len(destination_zip_code) != 8:
        return Response(
            {"error": {"code": "invalid_zip", "message": "Informe um CEP válido com oito números."}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Look up address
    destination = lookup_cep(destination_zip_code)
    dest_dict = None
    if destination:
        dest_dict = {
            "zip_code": f"{destination.zip_code[:5]}-{destination.zip_code[5:]}",
            "street": destination.street,
            "neighborhood": destination.neighborhood,
            "city": destination.city,
            "state": destination.state,
        }

    # Validate and build package
    try:
        package = validate_and_build_package(
            destination_zip_code=destination_zip_code,
            weight_grams=int(weight_grams),
            length_cm=length_cm,
            width_cm=width_cm,
            height_cm=height_cm,
            declared_value_cents=int(declared_value_cents),
        )
    except (TypeError, ValueError):
        return Response(
            {"error": {"code": "validation_error", "message": "Peso e valor declarado devem ser números inteiros."}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except FreightValidationError as e:
        return Response(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Dados do pacote inválidos.",
                    "field_errors": e.args[0] if e.args else {},
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    logger.info(
        "seller_authenticated=true seller_id=%s freight_calculate_started=true cep=%s*** weight=%d",
        seller.id,
        destination_zip_code[:5],
        int(weight_grams),
    )

    # Calculate freight
    try:
        options = calculate_freight(package)
    except FreightConfigurationError as e:
        return Response(
            {"error": {"code": "freight_not_configured", "message": str(e)}},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except FreightProviderUnavailable as e:
        return Response(
            {"error": {"code": "provider_unavailable", "message": str(e)}},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    formatted_options = []
    for i, opt in enumerate(options):
        provider_days = opt.get("provider_delivery_days")
        additional_days = opt.get("additional_delivery_days", 0)
        final_days = (
            provider_days + additional_days
            if provider_days is not None
            else None
        )
        price_cents = opt.get("price_cents", 0)

        formatted_options.append({
            "service_code": opt.get("service_code"),
            "service_name": opt.get("service_name"),
            "price_cents": price_cents,
            "formatted_price": format_price_cents(price_cents) if price_cents > 0 else None,
            "provider_delivery_days": provider_days,
            "additional_delivery_days": additional_days,
            "delivery_days": final_days,
            "official": opt.get("official"),
            "error": opt.get("error"),
            "is_best_option": i == 0 and price_cents > 0,
        })

    formatted_zip = f"{destination_zip_code[:5]}-{destination_zip_code[5:]}"

    response_data = {
        "data": {
            "destination": dest_dict
            or {
                "zip_code": formatted_zip,
                "street": "",
                "neighborhood": "",
                "city": "",
                "state": "",
            },
            "package": {
                "weight_grams": package.weight_grams,
                "length_cm": package.length_cm,
                "width_cm": package.width_cm,
                "height_cm": package.height_cm,
            },
            "options": formatted_options,
        }
    }

    return Response(response_data, status=status.HTTP_200_OK)
