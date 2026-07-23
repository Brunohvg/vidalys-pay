"""Validation contracts for the boleto API."""

import re

from rest_framework import serializers

from .models import BoletoStatus
from .validators import validate_cnpj


class BoletoCreateSerializer(serializers.Serializer):
    seller_id = serializers.UUIDField(required=False, write_only=True)
    cnpj = serializers.CharField(max_length=20)
    legal_name = serializers.CharField(max_length=200)
    trade_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    email = serializers.EmailField(max_length=254)
    phone = serializers.CharField(max_length=20)
    whatsapp_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    zip_code = serializers.CharField(max_length=10)
    street = serializers.CharField(max_length=200)
    number = serializers.CharField(max_length=20)
    complement = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    district = serializers.CharField(max_length=100)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(min_length=2, max_length=2)
    amount_cents = serializers.IntegerField(min_value=1)
    due_date = serializers.DateField()
    description = serializers.CharField(max_length=255)
    internal_reference = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    internal_notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)

    def validate_cnpj(self, value: str) -> str:
        try:
            validate_cnpj(value)
        except Exception as exc:
            raise serializers.ValidationError("CNPJ inválido.") from exc
        return re.sub(r"\D", "", value)

    def validate_zip_code(self, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) != 8:
            raise serializers.ValidationError("Informe um CEP com oito dígitos.")
        return digits

    def validate_phone(self, value: str) -> str:
        return _validate_brazilian_phone(value, required=True)

    def validate_whatsapp_phone(self, value: str) -> str:
        return _validate_brazilian_phone(value, required=False)

    def validate_state(self, value: str) -> str:
        if not value.isalpha():
            raise serializers.ValidationError("Informe uma UF válida.")
        return value.upper()


class BoletoListQuerySerializer(serializers.Serializer):
    seller_id = serializers.UUIDField(required=False, write_only=True)
    status = serializers.ChoiceField(
        choices=BoletoStatus.values,
        required=False,
        allow_blank=True,
        default="",
    )
    cursor = serializers.DateTimeField(required=False, allow_null=True, default=None)
    limit = serializers.IntegerField(min_value=1, max_value=100, required=False, default=20)
    due_from = serializers.DateField(required=False, allow_null=True, default=None)
    due_to = serializers.DateField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if attrs["due_from"] and attrs["due_to"] and attrs["due_from"] > attrs["due_to"]:
            raise serializers.ValidationError({"due_to": ["Deve ser igual ou posterior a due_from."]})
        return attrs


class BoletoSecondCopySerializer(serializers.Serializer):
    seller_id = serializers.UUIDField(required=False, write_only=True)
    due_date = serializers.DateField()


def _validate_brazilian_phone(value: str, *, required: bool) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not digits and not required:
        return ""
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) not in (10, 11):
        raise serializers.ValidationError("Informe um telefone brasileiro com DDD.")
    return digits
