"""Immutable data structures for freight module."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PackageData:
    destination_zip_code: str
    weight_grams: int
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal
    declared_value_cents: int = 0


@dataclass(frozen=True)
class FreightOption:
    provider: str
    service_code: str
    service_name: str
    price_cents: int
    delivery_days: int | None
    official: bool
    error: str | None = None


@dataclass(frozen=True)
class CorreiosToken:
    access_token: str
    expires_in: int
    token_type: str = "Bearer"
