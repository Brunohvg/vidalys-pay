"""Seller authentication decorators."""
from functools import wraps

from django.shortcuts import redirect


def seller_login_required(view_func):
    """Decorator that requires a valid seller session.

    For HTML page requests: redirects to session_invalid page.
    For API/JSON requests: returns 401 JSON.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request, "seller") or request.seller is None:
            if _is_html_request(request):
                return redirect("sellers:session_invalid")
            from django.http import JsonResponse
            return JsonResponse(
                {"error": {"code": "unauthorized", "message": "Sessão de vendedor inválida."}},
                status=401,
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def _is_html_request(request) -> bool:
    accept = request.META.get("HTTP_ACCEPT", "")
    return "text/html" in accept and "application/json" not in accept
