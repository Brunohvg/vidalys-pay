"""DRF authentication classes for API keys."""
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .auth import authenticate_api_key


class ApiKeyAuthentication(BaseAuthentication):
    """Authenticate requests using API Key in Authorization header.

    Format: Bearer vly_live_xxxxx
    """

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header:
            return None

        client = authenticate_api_key(auth_header)
        if client is None:
            raise AuthenticationFailed("Invalid or inactive API key.")

        return (client, None)

    def authenticate_header(self, request):
        return "Bearer"
