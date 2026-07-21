"""Seller authentication decorators."""
from functools import wraps

from django.http import JsonResponse


def seller_login_required(view_func):
    """Decorator that requires a valid seller session.

    Returns 401 JSON if not authenticated.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request, "seller") or request.seller is None:
            return JsonResponse(
                {"error": {"code": "unauthorized", "message": "Sessão de vendedor inválida."}},
                status=401,
            )
        return view_func(request, *args, **kwargs)

    return wrapper
