"""DRF authentication class for seller sessions."""
import logging

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger("apps.sellers")


class SellerPrincipal:
    """Lightweight user-like object for authenticated sellers.

    DRF requires request.user to have is_authenticated=True.
    This avoids needing a real Django User model for seller sessions.
    """

    def __init__(self, seller):
        self.id = seller.id
        self.pk = seller.pk
        self.seller = seller
        self.is_authenticated = True
        self.is_anonymous = False

    def __str__(self):
        return f"Seller:{self.seller.name}"


class SellerSessionAuthentication(BaseAuthentication):
    """Authenticate requests via seller session set by SellerSessionMiddleware.

    Reads request._request.seller (the underlying Django HttpRequest).
    Returns a SellerPrincipal as the user and the Seller as request.auth.
    """

    def authenticate(self, request):
        # Read from the underlying Django HttpRequest (set by SellerSessionMiddleware)
        seller = getattr(request._request, "seller", None) or getattr(request, "seller", None)

        if seller is None:
            # No seller session — let other auth classes try (e.g. ApiKeyAuthentication)
            return None

        if not seller.is_active:
            logger.warning(
                "SellerSessionAuthentication: vendedor inativo seller=%s",
                seller.id,
            )
            raise AuthenticationFailed(
                detail="Sua sessão expirou. Entre novamente.",
                code="seller_not_authenticated",
            )

        logger.debug("SellerSessionAuthentication: seller=%s authenticated", seller.id)

        principal = SellerPrincipal(seller)
        return (principal, seller)

    def authenticate_header(self, request):
        return "Session"
