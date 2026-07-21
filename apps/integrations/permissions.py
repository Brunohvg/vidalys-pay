"""DRF permission classes for API key scopes."""
from rest_framework.permissions import BasePermission


class HasScope(BasePermission):
    """Check if the authenticated API client has the required scope.

    Usage:
        permission_classes = [HasScope("payment_links:read")]
    """

    def __init__(self, scope: str):
        self.scope = scope

    def has_permission(self, request, view):
        # Seller session always has full access
        if hasattr(request, "seller") and request.seller is not None:
            return True

        # API key must have the required scope
        client = getattr(request, "user", None)
        if client is None or not hasattr(client, "scopes"):
            return False

        return self.scope in (client.scopes or [])
