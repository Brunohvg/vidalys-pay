"""Middleware for request ID tracking."""
import uuid

from django.utils.deprecation import MiddlewareMixin


class RequestIdMiddleware(MiddlewareMixin):
    """Attach a unique request_id to every request for logging."""

    def process_request(self, request):
        request.request_id = str(uuid.uuid4())
