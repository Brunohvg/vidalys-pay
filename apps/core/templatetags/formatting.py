"""Custom template filters for formatting monetary values."""
from decimal import ROUND_HALF_UP, Decimal

from django import template

register = template.Library()


@register.filter(name="format_brl")
def format_brl(value):
    """Format an integer (centavos) as BRL currency.

    Usage: {{ amount_cents|format_brl }}
    Output: R$ 1.000,00

    Examples:
        100     -> R$ 1,00
        1000    -> R$ 10,00
        10000   -> R$ 100,00
        100000  -> R$ 1.000,00
    """
    if value is None or value == "":
        return "R$ 0,00"

    try:
        cents = int(value)
    except (TypeError, ValueError):
        return "R$ 0,00"

    # Convert centavos to reais using Decimal for precision
    value_decimal = Decimal(str(cents)) / Decimal("100")
    # Round to 2 decimal places
    value_decimal = value_decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Format with Brazilian convention: dot for thousands, comma for decimal
    # Python format: 1000.00 -> "1,000.00" (English)
    # We need: 1.000,00 (Brazilian)
    formatted = f"{value_decimal:,.2f}"
    # Swap: first swap dots to temporary, then commas to dots, then temp to commas
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")

    return f"R$ {formatted}"
