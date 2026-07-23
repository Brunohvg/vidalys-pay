"""Backend forms for the reviewed boleto creation workflow."""
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError

from .validators import normalize_cnpj, validate_cnpj


class BoletoCreationForm(forms.Form):
    cnpj = forms.CharField(max_length=20)
    legal_name = forms.CharField(max_length=200)
    trade_name = forms.CharField(max_length=200, required=False)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20)
    whatsapp_phone = forms.CharField(max_length=20, required=False)
    zip_code = forms.CharField(max_length=10)
    street = forms.CharField(max_length=200)
    number = forms.CharField(max_length=20)
    complement = forms.CharField(max_length=100, required=False)
    district = forms.CharField(max_length=100)
    city = forms.CharField(max_length=100)
    state = forms.CharField(min_length=2, max_length=2)
    amount_display = forms.CharField(max_length=30)
    due_date = forms.DateField(input_formats=["%Y-%m-%d"])
    description = forms.CharField(max_length=255)
    internal_reference = forms.CharField(max_length=80, required=False)
    internal_notes = forms.CharField(required=False, widget=forms.Textarea)
    seller_id = forms.UUIDField(required=False)

    def clean_cnpj(self):
        cnpj = normalize_cnpj(self.cleaned_data["cnpj"])
        validate_cnpj(cnpj)
        return cnpj

    def clean_zip_code(self):
        zip_code = re.sub(r"\D", "", self.cleaned_data["zip_code"])
        if len(zip_code) != 8:
            raise ValidationError("Informe um CEP válido com oito dígitos.")
        return zip_code

    def clean_phone(self):
        return self._clean_phone("phone", required=True)

    def clean_whatsapp_phone(self):
        return self._clean_phone("whatsapp_phone", required=False)

    def _clean_phone(self, field: str, *, required: bool) -> str:
        phone = re.sub(r"\D", "", self.cleaned_data.get(field, ""))
        if phone.startswith("55") and len(phone) in {12, 13}:
            phone = phone[2:]
        if required and len(phone) not in {10, 11}:
            raise ValidationError("Informe um telefone com DDD.")
        if phone and len(phone) not in {10, 11}:
            raise ValidationError("Informe um telefone com DDD.")
        return phone

    def clean_state(self):
        return self.cleaned_data["state"].strip().upper()

    def clean_due_date(self):
        due_date = self.cleaned_data["due_date"]
        if due_date < date.today():
            raise ValidationError("O vencimento não pode estar no passado.")
        return due_date

    def clean_amount_display(self):
        raw = self.cleaned_data["amount_display"].strip()
        normalized = raw.replace("R$", "").replace(" ", "")
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        try:
            amount = Decimal(normalized).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            raise ValidationError("Informe um valor válido.") from None
        amount_cents = int(amount * 100)
        if amount_cents <= 0:
            raise ValidationError("O valor deve ser maior que zero.")
        return amount_cents
