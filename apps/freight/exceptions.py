"""Custom exceptions for the freight module."""


class FreightError(Exception):
    """Base exception for freight errors."""


class FreightConfigurationError(FreightError):
    """Invalid or missing freight configuration."""


class FreightAuthenticationError(FreightError):
    """Correios authentication failed (401, 403)."""


class FreightTimeoutError(FreightError):
    """Correios API timed out."""


class FreightConnectionError(FreightError):
    """Network error connecting to Correios API."""


class FreightProviderUnavailable(FreightError):
    """Correios API returned an unexpected HTTP error or is unavailable."""


class FreightValidationError(FreightError):
    """Invalid package data or CEP."""
