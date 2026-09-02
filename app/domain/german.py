from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from app.domain.models import AccountFolderMetadata, MoneyDirection, ParsedMoney

_MONEY_TOKEN = re.compile(
    r"(?<!\d)(?:-\s*)?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,4})?\s*(?:EUR|USD|€|%|-)?(?!\d)",
    re.IGNORECASE,
)


class GermanMoneyParser:
    """Strict parser for German financial notation using Decimal only."""

    def parse(self, raw: str, *, default_currency: str | None = None) -> ParsedMoney:
        text = raw.strip()
        match = _MONEY_TOKEN.search(text)
        if match is None:
            raise ValueError(f"No German amount found in {raw!r}")
        token = match.group(0).strip()
        is_percentage = "%" in token
        currency = self._currency(token, default_currency)
        negative = bool(re.match(r"^-\s*", token) or re.search(r"-\s*$", token))
        numeric = re.sub(r"(?:EUR|USD|€|%|-)", "", token, flags=re.IGNORECASE).strip()
        numeric = numeric.replace(".", "").replace(",", ".")
        try:
            amount = Decimal(numeric)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid German amount {raw!r}") from exc
        if negative:
            amount = -abs(amount)
        direction = MoneyDirection.DEBIT if amount < 0 else MoneyDirection.CREDIT
        return ParsedMoney(
            raw_amount=token,
            normalized_amount=amount,
            currency=currency,
            direction=direction,
            is_percentage=is_percentage,
        )

    def find_all(self, text: str, *, default_currency: str | None = None) -> list[ParsedMoney]:
        return [
            self.parse(match.group(0), default_currency=default_currency)
            for match in _MONEY_TOKEN.finditer(text)
        ]

    @staticmethod
    def _currency(token: str, default: str | None) -> str | None:
        upper = token.upper()
        if "USD" in upper:
            return "USD"
        if "EUR" in upper or "€" in token:
            return "EUR"
        return None if "%" in token else default


class DatePrecision(StrEnum):
    DAY = "day"
    MONTH = "month"


@dataclass(frozen=True, slots=True)
class ParsedGermanDate:
    value: date
    precision: DatePrecision
    raw: str


_MONTHS = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}


class GermanDateParser:
    def parse(self, raw: str) -> ParsedGermanDate:
        text = raw.strip().rstrip(".,")
        numeric = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})", text)
        if numeric:
            day, month, year = (int(item) for item in numeric.groups())
            year = 2000 + year if year < 100 else year
            return ParsedGermanDate(date(year, month, day), DatePrecision.DAY, raw)
        month_numeric = re.fullmatch(r"(\d{1,2})/(\d{4})", text)
        if month_numeric:
            month, year = (int(item) for item in month_numeric.groups())
            return ParsedGermanDate(date(year, month, 1), DatePrecision.MONTH, raw)
        named = re.fullmatch(r"(?:(\d{1,2})\.\s*)?([A-Za-zÄÖÜäöüß]+)\s+(\d{4})", text)
        if named:
            day_raw, month_raw, year_raw = named.groups()
            named_month = _MONTHS.get(month_raw.casefold())
            if named_month is None:
                raise ValueError(f"Unknown German month in {raw!r}")
            precision = DatePrecision.DAY if day_raw else DatePrecision.MONTH
            return ParsedGermanDate(
                date(int(year_raw), named_month, int(day_raw or "1")), precision, raw
            )
        raise ValueError(f"Unsupported German date {raw!r}")


def normalize_german_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text).replace("\u00ad", "")
    normalized = re.sub(r"([A-Za-zÄÖÜäöüß])\-\s*\r?\n\s*([a-zäöüß])", r"\1\2", normalized)
    normalized = re.sub(r"[\t\f\v ]+", " ", normalized)
    normalized = re.sub(r" *\r?\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def parse_account_folder(folder_path: str) -> AccountFolderMetadata:
    parts = [part for part in re.split(r"[/\\]", folder_path) if part]
    label = next((part for part in reversed(parts) if re.match(r"^\d{4,}_", part)), None)
    code: str | None = None
    role: str | None = None
    currency: str | None = None
    if label:
        match = re.match(r"^(\d+)_?(.*)$", label)
        if match:
            code = match.group(1)
            suffix = match.group(2).casefold()
            if "ausgaben" in suffix:
                role = "expenses"
            elif "einnahmen" in suffix:
                role = "income"
            elif "darlehen" in suffix:
                role = "loan"
            if "usd" in suffix:
                currency = "USD"
            elif "eur" in suffix:
                currency = "EUR"
    return AccountFolderMetadata(
        account_label=label,
        account_code=code,
        account_role=role,
        expected_currency=currency,
        folder_path=folder_path,
    )
