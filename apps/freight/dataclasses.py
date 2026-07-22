"""Immutable data structures for freight module."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PackageData:
    destination_zip_code: str
    weight_grams: int
    length_cm: str
    width_cm: str
    height_cm: str
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


@dataclass(frozen=True)
class CEPAddressData:
    zip_code: str
    street: str
    neighborhood: str
    city: str
    state: str
    source: str = "viacep"
