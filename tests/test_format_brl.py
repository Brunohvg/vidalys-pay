"""Tests for the format_brl template filter."""
import pytest

from apps.core.templatetags.formatting import format_brl


@pytest.mark.parametrize(
    ("cents", "expected"),
    [
        (0, "R$ 0,00"),
        (1, "R$ 0,01"),
        (100, "R$ 1,00"),
        (500, "R$ 5,00"),
        (999, "R$ 9,99"),
        (1000, "R$ 10,00"),
        (1500, "R$ 15,00"),
        (9999, "R$ 99,99"),
        (10000, "R$ 100,00"),
        (10001, "R$ 100,01"),
        (50000, "R$ 500,00"),
        (100000, "R$ 1.000,00"),
        (1000000, "R$ 10.000,00"),
        (1234567, "R$ 12.345,67"),
        (99999999, "R$ 999.999,99"),
    ],
    ids=[
        "zero",
        "one_cent",
        "1_real",
        "5_reais",
        "9.99",
        "10_reais",
        "15_reais",
        "99.99",
        "100_reais",
        "100.01",
        "500_reais",
        "1000_reais",
        "10000_reais",
        "12345.67",
        "999999.99",
    ],
)
def test_format_brl(cents, expected):
    assert format_brl(cents) == expected


def test_format_brl_none():
    assert format_brl(None) == "R$ 0,00"


def test_format_brl_empty_string():
    assert format_brl("") == "R$ 0,00"


def test_format_brl_invalid_string():
    assert format_brl("abc") == "R$ 0,00"


def test_format_brl_float():
    """Float values should be truncated to int (centavos are always whole)."""
    assert format_brl(1000.0) == "R$ 10,00"


def test_format_brl_negative():
    """Negative values should work (e.g. refunds)."""
    assert format_brl(-1000) == "R$ -10,00"
