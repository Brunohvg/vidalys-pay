"""Bounded, cache-backed rate limiting for sensitive endpoints."""
import hashlib
import time
from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse


def _counter_key(scope: str, identity: str, window_seconds: int) -> str:
    window = int(time.time()) // window_seconds
    digest = hashlib.sha256(f"{scope}:{identity}".encode()).hexdigest()
    return f"rate-limit:{digest}:{window}"


def _increment(key: str, window_seconds: int) -> int:
    if cache.add(key, 1, timeout=window_seconds + 1):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds + 1)
        return 1


def rate_limit(max_requests: int = 60, window_seconds: int = 60):
    """Limit each endpoint independently using the configured Django cache."""
    def decorator(view_func):
        scope = f"{view_func.__module__}.{view_func.__qualname__}"

        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            counter_key = _counter_key(scope, _get_rate_limit_identity(request), window_seconds)
            current = _increment(counter_key, window_seconds)
            remaining = max(0, max_requests - current)
            reset_at = (int(time.time()) // window_seconds + 1) * window_seconds

            if current > max_requests:
                return JsonResponse(
                    {"error": {"code": "rate_limit_exceeded", "message": "Muitas requisições. Tente novamente em breve."}},
                    status=429,
                    headers={
                        "Retry-After": str(max(1, reset_at - int(time.time()))),
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_at),
                    },
                )

            response = view_func(request, *args, **kwargs)
            response["X-RateLimit-Limit"] = str(max_requests)
            response["X-RateLimit-Remaining"] = str(remaining)
            response["X-RateLimit-Reset"] = str(reset_at)
            return response

        return wrapper

    return decorator


def _get_rate_limit_identity(request) -> str:
    seller = getattr(request, "seller", None)
    if seller:
        return f"seller:{seller.id}"

    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        token_digest = hashlib.sha256(auth_header[7:].encode()).hexdigest()
        return f"apikey:{token_digest}"

    # Coolify/Traefik supplies the original address as the first forwarded value.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",", 1)[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "unknown")
    return f"ip:{ip}"
