"""Freight API endpoints."""
import logging

from rest_framework import status
from rest_framework.decorators import api_view
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
@rate_limit(max_requests=20, window_seconds=60)
@seller_login_required
def calculate_freight_view(request: Request) -> Response:
    data = request.data
    seller = request.seller

    destination_zip_code = (data.get("destination_zip_code") or "").strip().replace("-", "")
    weight_grams = data.get("weight_grams", 0)
    length_cm = data.get("length_cm", 0)
    width_cm = data.get("width_cm", 0)
    height_cm = data.get("height_cm", 0)
    declared_value_cents = data.get("declared_value_cents", 0)

    try:
        package = validate_and_build_package(
            destination_zip_code=destination_zip_code,
            weight_grams=int(weight_grams),
            length_cm=float(length_cm),
            width_cm=float(width_cm),
            height_cm=float(height_cm),
            declared_value_cents=int(declared_value_cents),
        )
    except FreightValidationError as e:
        return Response(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Dados do pacote invalidos.",
                    "field_errors": e.args[0] if e.args else {},
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    logger.info(
        "Calculo de frete: seller=%s cep=%s*** weight=%d",
        seller.id,
        destination_zip_code[:5],
        int(weight_grams),
    )

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

    destination = lookup_cep(destination_zip_code)

    formatted_options = []
    for opt in options:
        formatted_options.append({
            "service_code": opt.service_code,
            "service_name": opt.service_name,
            "price_cents": opt.price_cents,
            "formatted_price": format_price_cents(opt.price_cents) if opt.price_cents > 0 else None,
            "delivery_days": opt.delivery_days,
            "official": opt.official,
            "error": opt.error,
        })

    response_data = {
        "data": {
            "destination": destination
            or {
                "zip_code": destination_zip_code,
                "city": None,
                "state": None,
            },
            "options": formatted_options,
        }
    }

    return Response(response_data, status=status.HTTP_200_OK)
