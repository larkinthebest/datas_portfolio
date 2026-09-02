from __future__ import annotations

import re
from datetime import date

from app.domain.german import GermanDateParser, GermanMoneyParser, normalize_german_text
from app.domain.models import BankTransaction

_DATE_PATTERN = re.compile(r"(?<!\d)(\d{1,2}\.\d{1,2}\.(?:\d{2}|\d{4}))(?!\d)")
_BIC_PATTERN = re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b", re.IGNORECASE)
_IBAN_LENGTHS = {
    "AT": 20,
    "BE": 16,
    "CH": 21,
    "DE": 22,
    "ES": 24,
    "FR": 27,
    "GB": 22,
    "IT": 27,
    "LU": 20,
    "NL": 18,
}


class GermanBankStatementParser:
    version = "german_bank_statement_parser:v3"

    def __init__(self) -> None:
        self.money = GermanMoneyParser()
        self.dates = GermanDateParser()

    def parse(self, text: str, *, statement_page: int | None = None) -> list[BankTransaction]:
        normalized = normalize_german_text(text)
        currency = self._find_currency(normalized)
        date_matches = list(_DATE_PATTERN.finditer(normalized))
        transactions: list[BankTransaction] = []
        for index, match in enumerate(date_matches):
            start = match.start()
            end = (
                date_matches[index + 1].start()
                if index + 1 < len(date_matches)
                else len(normalized)
            )
            segment = normalized[start:end].strip()
            if not self._looks_like_transaction(segment):
                continue
            amount_candidates = self.money.find_all(segment, default_currency=currency)
            amount_candidates = [
                item
                for item in amount_candidates
                if not item.is_percentage and "," in item.raw_amount
            ]
            if not amount_candidates:
                continue
            amount = amount_candidates[-1]
            booking_date = self._safe_date(match.group(1))
            if booking_date is None:
                continue
            value_date = self._field_date(segment, ("Valuta", "Valutadatum"))
            transaction = BankTransaction(
                statement_page=statement_page,
                booking_date=booking_date,
                value_date=value_date,
                amount=amount.normalized_amount,
                currency=amount.currency or currency,
                direction=amount.direction,
                counterparty=self._bounded(
                    self._counterparty(segment, match.group(1)), max_length=1000
                ),
                iban=self._iban(segment),
                bic=self._bic(segment),
                reference=self._field(segment, ("Referenz", "Zahlungsreferenz")),
                booking_text=self._field(segment, ("Buchungstext", "Verwendungszweck")),
                end_to_end_reference=self._bounded(
                    self._field(
                        segment,
                        ("End-to-End-Ref.", "End-to-End-Ref", "End-to-End-Referenz"),
                    ),
                    max_length=500,
                ),
                mandate_reference=self._bounded(
                    self._field(segment, ("Mandatsref.", "Mandatsreferenz")),
                    max_length=500,
                ),
                creditor_id=self._bounded(
                    self._field(segment, ("Gläubiger-ID", "Glaeubiger-ID")),
                    max_length=500,
                ),
                raw_text=segment,
            )
            transactions.append(transaction)
        return transactions

    @staticmethod
    def _find_currency(text: str) -> str:
        match = re.search(r"Kontowährung\s*[:\s]\s*(EUR|USD)", text, re.I)
        if match:
            return match.group(1).upper()
        return "USD" if re.search(r"\bUSD\b", text) else "EUR"

    @staticmethod
    def _looks_like_transaction(segment: str) -> bool:
        return bool(re.search(r"\d[\d.]*,\d{2}\s*(?:EUR|USD|€|-)?", segment, re.I))

    def _field_date(self, text: str, labels: tuple[str, ...]) -> date | None:
        value = self._field(text, labels)
        if not value:
            return None
        match = _DATE_PATTERN.search(value)
        return self._safe_date(match.group(1)) if match else None

    def _safe_date(self, raw: str) -> date | None:
        try:
            return self.dates.parse(raw).value
        except ValueError:
            return None

    @staticmethod
    def _field(text: str, labels: tuple[str, ...]) -> str | None:
        label_pattern = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"(?:{label_pattern})\s*:?\s*([^\n]+)", text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    @classmethod
    def _iban(cls, text: str) -> str | None:
        value = cls._field(text, ("IBAN",))
        if not value:
            return None
        compact = re.sub(r"[^A-Z0-9]", "", value.upper())
        if not re.match(r"^[A-Z]{2}\d{2}", compact):
            return None
        expected_length = _IBAN_LENGTHS.get(compact[:2])
        if expected_length is None or len(compact) < expected_length:
            return None
        return compact[:expected_length]

    @classmethod
    def _bic(cls, text: str) -> str | None:
        value = cls._field(text, ("BIC",))
        if not value:
            return None
        match = _BIC_PATTERN.search(value)
        return match.group(0).upper() if match else None

    @staticmethod
    def _bounded(value: str | None, *, max_length: int) -> str | None:
        return value[:max_length] if value else None

    @staticmethod
    def _counterparty(segment: str, booking_date_raw: str) -> str | None:
        lines = [line.strip() for line in segment.splitlines() if line.strip()]
        ignored = re.compile(
            r"^(?:Buchungsdatum|Valuta|Valutadatum|Verwendungszweck|End-to-End|Mandats|"
            r"Gläubiger|Glaeubiger|IBAN|BIC|Buchungstext)",
            re.I,
        )
        candidates: list[str] = []
        for line in lines:
            cleaned = line.replace(booking_date_raw, "").strip(" :-")
            if not cleaned or ignored.match(cleaned):
                continue
            if re.fullmatch(r"[\d.]+,\d{2}\s*(?:EUR|USD|€|-)?", cleaned, re.I):
                continue
            candidates.append(cleaned)
        return " ".join(candidates[:2]) or None
