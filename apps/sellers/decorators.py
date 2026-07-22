"""Seller authentication decorators."""
import logging
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect

logger = logging.getLogger("apps.sellers")


def seller_login_required(view_func):
    """Decorator that requires a valid seller session.

    For HTML page requests: redirects to session_invalid page.
    For API/JSON requests: returns standardized 401 JSON.

    Works with both Django HttpRequest and DRF Request.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        seller = _get_seller(request)

        if seller is None:
            if _is_html_request(request):
                return redirect("sellers:session_invalid")
            return JsonResponse(
                {
                    "error": {
                        "code": "seller_not_authenticated",
                        "message": "Sua sessão expirou. Entre novamente.",
                    }
                },
                status=401,
            )

        if not seller.is_active:
            logger.warning(
                "seller_login_required: vendedor inativo seller=%s",
                seller.id,
            )
            if _is_html_request(request):
                return redirect("sellers:session_invalid")
            return JsonResponse(
                {
                    "error": {
                        "code": "seller_not_authenticated",
                        "message": "Sua sessão expirou. Entre novamente.",
                    }
                },
                status=401,
            )

        return view_func(request, *args, **kwargs)

    return wrapper


def _get_seller(request):
    """Extract seller from request, handling both DRF and Django requests."""
    # Try direct attribute first (Django HttpRequest)
    seller = getattr(request, "seller", None)
    if seller is not None:
        return seller

    # Try underlying Django HttpRequest (DRF Request wraps it)
    inner_request = getattr(request, "_request", None)
    if inner_request is not None:
        seller = getattr(inner_request, "seller", None)
        if seller is not None:
            return seller

    return None


def _is_html_request(request) -> bool:
    accept = request.META.get("HTTP_ACCEPT", "")
    return "text/html" in accept and "application/json" not in accept
