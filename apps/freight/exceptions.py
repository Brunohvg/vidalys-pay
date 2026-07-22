"""Custom exceptions for the freight module."""


class FreightError(Exception):
    """Base exception for freight errors."""


class FreightConfigurationError(FreightError):
    """Invalid or missing freight configuration."""


class FreightAuthenticationError(FreightError):
    """Correios authentication failed."""


class FreightProviderUnavailable(FreightError):
    """Correios API is unavailable or timed out."""


class FreightValidationError(FreightError):
    """Invalid package data or CEP."""
