from datetime import date
from decimal import Decimal

from app.domain.banking import GermanBankStatementParser
from app.domain.models import MoneyDirection


def test_bank_statement_golden_fixture() -> None:
    source = """Kontoauszug
Kontowährung: EUR
Buchungsdatum: 01.12.2025
WEG Beispielstraße 41
299,85-
Lastschrift Hausgeld 12.2025
End-to-End-Ref.: TEST123
"""
    transactions = GermanBankStatementParser().parse(source, statement_page=1)
    assert len(transactions) == 1
    transaction = transactions[0]
    assert transaction.booking_date == date(2025, 12, 1)
    assert transaction.amount == Decimal("-299.85")
    assert transaction.direction == MoneyDirection.DEBIT
    assert transaction.counterparty and "WEG" in transaction.counterparty
    assert transaction.end_to_end_reference == "TEST123"
    assert transaction.statement_page == 1


def test_non_transaction_date_is_ignored() -> None:
    assert GermanBankStatementParser().parse("Abrechnungszeitraum 01.01.2025 ohne Betrag") == []


def test_iban_and_bic_do_not_capture_neighboring_text() -> None:
    source = """Kontoauszug
Kontowährung: EUR
Buchungsdatum: 30.06.2017
Auszug-Nr. 7 Seite-Nr. 3
IBAN: DE89 5004 0000 0600 0806 08 USt-IdNr.: DE 114 103 514
BIC : COBADEFFXXX International Wealth Management I
Saldo nach Abschluss 48.253,37 EUR
"""
    transactions = GermanBankStatementParser().parse(source)

    assert len(transactions) == 1
    assert transactions[0].iban == "DE89500400000600080608"
    assert transactions[0].bic == "COBADEFFXXX"


def test_invalid_calendar_date_is_skipped_without_losing_valid_transactions() -> None:
    source = """Kontoauszug
Kontowährung: EUR
31.02.2024 Fehlerhafte OCR-Zeile 10,00 EUR
29.02.2024 Gültige Buchung 20,00 EUR
"""

    transactions = GermanBankStatementParser().parse(source)

    assert len(transactions) == 1
    assert transactions[0].booking_date == date(2024, 2, 29)
    assert transactions[0].amount == Decimal("20.00")
