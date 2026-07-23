"""Backend authorization rules for the boleto domain."""
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied

from apps.sellers.models import Seller


@dataclass(frozen=True)
class BoletoActor:
    """Authenticated actor resolved from the two authentication domains."""

    user: object | None = None
    seller: Seller | None = None

    def __post_init__(self):
        if bool(self.user) == bool(self.seller):
            raise ValueError("Informe exatamente um ator autenticado.")

    @property
    def is_manager(self) -> bool:
        return bool(
            self.user
            and getattr(self.user, "is_authenticated", False)
            and getattr(self.user, "is_superuser", False)
        )

    @property
    def is_seller(self) -> bool:
        return self.seller is not None


def resolve_creation_seller(*, actor: BoletoActor, requested_seller: Seller | None = None) -> Seller:
    """Resolve the responsible seller without trusting client-provided ownership."""
    if actor.is_manager:
        if requested_seller is None:
            raise PermissionDenied("Selecione o vendedor responsável.")
        seller = requested_seller
    elif actor.is_seller:
        if requested_seller is not None and requested_seller.pk != actor.seller.pk:
            raise PermissionDenied("O vendedor não pode criar boleto para outro vendedor.")
        seller = actor.seller
    else:
        raise PermissionDenied("Ator não autorizado a criar boletos.")

    if not seller.is_active:
        raise PermissionDenied("Vendedor inativo.")
    return seller


def scope_boletos(queryset, *, actor: BoletoActor):
    """Apply object-level visibility before a boleto is resolved by its UUID."""
    if actor.is_manager:
        return queryset
    if actor.is_seller and actor.seller.is_active:
        return queryset.filter(seller=actor.seller)
    return queryset.none()


def can_view_technical_data(*, actor: BoletoActor) -> bool:
    """Technical provider and webhook payloads are manager-only."""
    return actor.is_manager
