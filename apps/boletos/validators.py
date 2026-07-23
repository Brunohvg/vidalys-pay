"""Normalization and validation for Brazilian company documents."""
import re

from django.core.exceptions import ValidationError


def normalize_cnpj(value: object) -> str:
    """Return only decimal digits from an arbitrary CNPJ representation."""
    return re.sub(r"\D", "", str(value or ""))


def is_valid_cnpj(value: object) -> bool:
    """Validate length, repeated sequences and both CNPJ check digits."""
    cnpj = normalize_cnpj(value)
    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        return False

    first_weights = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    second_weights = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)

    def check_digit(digits: str, weights: tuple[int, ...]) -> int:
        remainder = sum(int(digit) * weight for digit, weight in zip(digits, weights, strict=True)) % 11
        return 0 if remainder < 2 else 11 - remainder

    first_digit = check_digit(cnpj[:12], first_weights)
    second_digit = check_digit(cnpj[:13], second_weights)
    return cnpj[-2:] == f"{first_digit}{second_digit}"


def validate_cnpj(value: object) -> None:
    """Django validator for a normalized, mathematically valid CNPJ."""
    cnpj = normalize_cnpj(value)
    if len(cnpj) != 14:
        raise ValidationError(
            "O CNPJ deve conter exatamente 14 dígitos.",
            code="invalid_cnpj_length",
        )
    if not is_valid_cnpj(cnpj):
        raise ValidationError("CNPJ inválido.", code="invalid_cnpj")
