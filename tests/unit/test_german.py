from datetime import date
from decimal import Decimal

import pytest

from app.domain.german import (
    DatePrecision,
    GermanDateParser,
    GermanMoneyParser,
    normalize_german_text,
    parse_account_folder,
)
from app.domain.models import MoneyDirection


@pytest.mark.parametrize(
    ("raw", "amount", "direction", "currency"),
    [
        ("1.234,56 €", Decimal("1234.56"), MoneyDirection.CREDIT, "EUR"),
        ("12.500,00", Decimal("12500.00"), MoneyDirection.CREDIT, "EUR"),
        ("299,85-", Decimal("-299.85"), MoneyDirection.DEBIT, "EUR"),
        ("-299,85", Decimal("-299.85"), MoneyDirection.DEBIT, "EUR"),
        ("299,85 -", Decimal("-299.85"), MoneyDirection.DEBIT, "EUR"),
        ("2.500,00", Decimal("2500.00"), MoneyDirection.CREDIT, "EUR"),
        ("8.575,50-", Decimal("-8575.50"), MoneyDirection.DEBIT, "EUR"),
    ],
)
def test_german_money(raw: str, amount: Decimal, direction: MoneyDirection, currency: str) -> None:
    result = GermanMoneyParser().parse(raw, default_currency="EUR")
    assert result.normalized_amount == amount
    assert result.direction == direction
    assert result.currency == currency


def test_percentage_is_not_money_currency() -> None:
    result = GermanMoneyParser().parse("19,00 %", default_currency="EUR")
    assert result.normalized_amount == Decimal("19.00")
    assert result.is_percentage is True
    assert result.currency is None


@pytest.mark.parametrize(
    ("raw", "expected", "precision"),
    [
        ("31.12.2025", date(2025, 12, 31), DatePrecision.DAY),
        ("31.12.25", date(2025, 12, 31), DatePrecision.DAY),
        ("1. Januar 2025", date(2025, 1, 1), DatePrecision.DAY),
        ("01/2025", date(2025, 1, 1), DatePrecision.MONTH),
        ("Januar 2025", date(2025, 1, 1), DatePrecision.MONTH),
    ],
)
def test_german_dates(raw: str, expected: date, precision: DatePrecision) -> None:
    result = GermanDateParser().parse(raw)
    assert result.value == expected
    assert result.precision == precision


def test_normalization_preserves_german_symbols_and_repairs_hyphenation() -> None:
    source = "Betriebs-\nkosten  für  Größe § 19: 1.234,56 €\u00ad"
    assert normalize_german_text(source) == "Betriebskosten für Größe § 19: 1.234,56 €"


def test_folder_metadata() -> None:
    result = parse_account_folder("Bank/080606_USD/2025")
    assert result.account_code == "080606"
    assert result.expected_currency == "USD"
    assert result.folder_path == "Bank/080606_USD/2025"
