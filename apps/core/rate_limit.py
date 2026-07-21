"""Simple rate limiting for API endpoints."""
import time
from collections import defaultdict
from functools import wraps
from threading import Lock

from django.http import JsonResponse


class RateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self):
        self._requests = defaultdict(list)
        self._lock = Lock()

    def is_limited(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if a key has exceeded the rate limit.

        Args:
            key: Rate limit key (e.g., IP, seller_id, api_client_id)
            max_requests: Maximum requests allowed in the window
            window_seconds: Time window in seconds

        Returns:
            True if rate limited, False otherwise
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Clean old entries
            self._requests[key] = [
                t for t in self._requests[key] if t > cutoff
            ]

            # Check limit
            if len(self._requests[key]) >= max_requests:
                return True

            # Record request
            self._requests[key].append(now)
            return False

    def get_remaining(self, key: str, max_requests: int, window_seconds: int) -> int:
        """Get remaining requests in the current window."""
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            recent = [t for t in self._requests.get(key, []) if t > cutoff]
            return max(0, max_requests - len(recent))


# Global rate limiter instance
_rate_limiter = RateLimiter()


def rate_limit(max_requests: int = 60, window_seconds: int = 60):
    """Decorator for rate limiting views.

    Usage:
        @rate_limit(max_requests=60, window_seconds=60)
        def my_view(request):
            ...
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Determine rate limit key
            key = _get_rate_limit_key(request)

            if _rate_limiter.is_limited(key, max_requests, window_seconds):
                remaining = _rate_limiter.get_remaining(key, max_requests, window_seconds)
                return JsonResponse(
                    {
                        "error": {
                            "code": "rate_limit_exceeded",
                            "message": "Muitas requisições. Tente novamente em breve.",
                        }
                    },
                    status=429,
                    headers={
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + window_seconds),
                    },
                )

            response = view_func(request, *args, **kwargs)

            # Add rate limit headers
            remaining = _rate_limiter.get_remaining(key, max_requests, window_seconds)
            response["X-RateLimit-Limit"] = str(max_requests)
            response["X-RateLimit-Remaining"] = str(remaining)

            return response

        return wrapper

    return decorator


def _get_rate_limit_key(request) -> str:
    """Generate a rate limit key based on request context."""
    # Seller session
    seller = getattr(request, "seller", None)
    if seller:
        return f"seller:{seller.id}"

    # API key
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        # Use first 12 chars of token as key
        token = auth_header[7:19]
        return f"apikey:{token}"

    # Fall back to IP
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    ip = x_forwarded.split(",")[0].strip() if x_forwarded else request.META.get("REMOTE_ADDR", "unknown")

    return f"ip:{ip}"
