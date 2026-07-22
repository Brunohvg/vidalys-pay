"""Seller authentication middleware."""
import logging

from .services import get_seller_from_session

logger = logging.getLogger("apps.sellers")


class SellerSessionMiddleware:
    """Attach seller to request if valid session exists."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.seller = get_seller_from_session(request)
        response = self.get_response(request)
        return response
