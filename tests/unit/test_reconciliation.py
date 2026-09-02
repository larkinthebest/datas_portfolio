from datetime import date
from decimal import Decimal

from app.domain.reconciliation import ReconciliationRecord, score_reconciliation


def test_explainable_probable_reconciliation() -> None:
    transaction = ReconciliationRecord(
        amount=Decimal("1250.00"),
        currency="EUR",
        event_date=date(2025, 6, 12),
        counterparty="Muster GmbH Berlin",
        reference="Zahlung Rechnung RE-2025-17",
    )
    invoice = ReconciliationRecord(
        amount=Decimal("1250.00"),
        currency="EUR",
        event_date=date(2025, 6, 10),
        counterparty="Muster GmbH",
        invoice_number="RE-2025-17",
    )
    result = score_reconciliation(transaction, invoice)
    assert result.status == "probable_match"
    assert result.score >= Decimal("0.70")
    assert "exact amount" in result.reasons
    assert "invoice number found in payment reference" in result.reasons


def test_currency_conflict_is_explicit() -> None:
    left = ReconciliationRecord(amount=Decimal("10"), currency="EUR", event_date=date(2025, 1, 1))
    right = ReconciliationRecord(amount=Decimal("10"), currency="USD", event_date=date(2025, 1, 1))
    result = score_reconciliation(left, right)
    assert "currency differs" in result.conflicts
