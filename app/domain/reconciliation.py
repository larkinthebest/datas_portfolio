from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class ReconciliationRecord(BaseModel):
    amount: Decimal
    currency: str
    event_date: date
    counterparty: str = ""
    iban: str = ""
    reference: str = ""
    invoice_number: str = ""


class ReconciliationWeights(BaseModel):
    amount: Decimal = Decimal("0.30")
    currency: Decimal = Decimal("0.10")
    date: Decimal = Decimal("0.15")
    counterparty: Decimal = Decimal("0.10")
    iban: Decimal = Decimal("0.10")
    reference: Decimal = Decimal("0.10")
    invoice_number: Decimal = Decimal("0.15")


class ReconciliationResult(BaseModel):
    status: str
    score: Decimal = Field(ge=0, le=1)
    component_scores: dict[str, Decimal]
    reasons: list[str]
    conflicts: list[str]


def score_reconciliation(
    transaction: ReconciliationRecord,
    document: ReconciliationRecord,
    weights: ReconciliationWeights | None = None,
) -> ReconciliationResult:
    weights = weights or ReconciliationWeights()
    day_delta = abs((transaction.event_date - document.event_date).days)
    component = {
        "amount": Decimal("1") if transaction.amount == document.amount else Decimal("0"),
        "currency": Decimal("1") if transaction.currency == document.currency else Decimal("0"),
        "date": max(Decimal("0"), Decimal("1") - Decimal(day_delta) / Decimal("30")),
        "counterparty": _text_score(transaction.counterparty, document.counterparty),
        "iban": _exact_optional(transaction.iban, document.iban),
        "reference": _contains_score(transaction.reference, document.reference),
        "invoice_number": _contains_score(transaction.reference, document.invoice_number),
    }
    score = sum(component[name] * getattr(weights, name) for name in component).quantize(
        Decimal("0.0001")
    )
    reasons: list[str] = []
    conflicts: list[str] = []
    if component["amount"] == 1:
        reasons.append("exact amount")
    else:
        conflicts.append("amount differs")
    if component["currency"] == 1:
        reasons.append("same currency")
    else:
        conflicts.append("currency differs")
    if day_delta <= 7:
        reasons.append(f"dates differ by {day_delta} days")
    if component["invoice_number"] == 1:
        reasons.append("invoice number found in payment reference")
    if conflicts and score >= Decimal("0.70"):
        status = "conflict"
    elif score >= Decimal("0.95"):
        status = "exact_match"
    elif score >= Decimal("0.70"):
        status = "probable_match"
    elif score >= Decimal("0.45"):
        status = "ambiguous"
    else:
        status = "unmatched"
    return ReconciliationResult(
        status=status,
        score=score,
        component_scores=component,
        reasons=reasons,
        conflicts=conflicts,
    )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _text_score(left: str, right: str) -> Decimal:
    left_tokens = set(_normalize(left).split())
    right_tokens = set(_normalize(right).split())
    if not left_tokens or not right_tokens:
        return Decimal("0")
    return Decimal(len(left_tokens & right_tokens)) / Decimal(len(left_tokens | right_tokens))


def _exact_optional(left: str, right: str) -> Decimal:
    return (
        Decimal("1") if left and right and _normalize(left) == _normalize(right) else Decimal("0")
    )


def _contains_score(left: str, right: str) -> Decimal:
    left_n, right_n = _normalize(left), _normalize(right)
    return (
        Decimal("1")
        if left_n and right_n and (left_n in right_n or right_n in left_n)
        else Decimal("0")
    )
