"""Validation contracts for the payment links API."""

import re

from rest_framework import serializers

from .models import PaymentLinkStatus


class PaymentLinkCreateSerializer(serializers.Serializer):
    seller_id = serializers.UUIDField(required=False, write_only=True)
    reference = serializers.CharField(max_length=80, trim_whitespace=True)
    amount_cents = serializers.IntegerField(min_value=1)
    installments = serializers.ChoiceField(choices=(1, 2, 3))
    customer_name = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
    )
    customer_phone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
    )
    description = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
    expires_in_minutes = serializers.IntegerField(
        min_value=10,
        max_value=43200,
        required=False,
        allow_null=True,
        default=None,
    )

    def validate_customer_phone(self, value: str | None) -> str:
        """Accept the Brazilian UI mask and persist a canonical E.164 phone."""
        if not value:
            return ""
        digits = re.sub(r"\D", "", value)
        if value.strip().startswith("+") and 8 <= len(digits) <= 15 and not digits.startswith("0"):
            return f"+{digits}"
        if len(digits) in (10, 11):
            return f"+55{digits}"
        if digits.startswith("55") and len(digits) in (12, 13):
            return f"+{digits}"
        raise serializers.ValidationError(
            "Use um telefone brasileiro com DDD ou o formato E.164, por exemplo +5531999999999."
        )


class PaymentLinkListQuerySerializer(serializers.Serializer):
    seller_id = serializers.UUIDField(required=False, write_only=True)
    status = serializers.ChoiceField(
        choices=PaymentLinkStatus.values,
        required=False,
        allow_blank=True,
        default="",
    )
    cursor = serializers.DateTimeField(required=False, allow_null=True, default=None)
    limit = serializers.IntegerField(min_value=1, max_value=100, required=False, default=20)
