"""Middleware for request ID tracking."""
import uuid

from django.utils.deprecation import MiddlewareMixin


class RequestIdMiddleware(MiddlewareMixin):
    """Attach a unique request_id to every request for logging."""

    def process_request(self, request):
        request.request_id = str(uuid.uuid4())

    def process_response(self, request, response):
        request_id = getattr(request, "request_id", "")
        if request_id:
            response["X-Request-ID"] = request_id
        return response
