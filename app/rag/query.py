from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.german import normalize_german_text

GERMAN_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "отоплен": ("Heizkosten", "Heizkostenabrechnung", "Heizung"),
    "коммуналь": (
        "Betriebskosten",
        "Betriebskostenabrechnung",
        "Nebenkosten",
        "Heizkosten",
        "Wasserkosten",
    ),
    "налог": ("Steuer", "Steuerbescheid", "Finanzamt", "Grundsteuer"),
    "кредит": ("Darlehen", "Darlehensvertrag", "Tilgung", "Zinsen"),
    "процент": ("Zinsen", "Darlehenszinsen"),
    "страхов": ("Versicherung", "Versicherungsbeitrag"),
    "аренд": ("Miete", "Mietvertrag", "Mieteinnahmen"),
    "счет": ("Rechnung", "Rechnungsnummer", "Gesamtbetrag"),
    "расход": ("Ausgaben", "Betriebsausgaben", "Kosten"),
    "доход": ("Einnahmen", "Gutschrift"),
}

IDENTIFIER_PATTERNS = (
    re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b", re.I),
    re.compile(r"\b(?:TEST|E2E|REF)[-A-Z0-9]{3,}\b", re.I),
    re.compile(r"\b\d{6,}\b"),
)


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
    original_query: str
    normalized_query: str
    expanded_terms: tuple[str, ...]
    exact_identifiers: tuple[str, ...]

    @property
    def search_text(self) -> str:
        return " ".join((self.normalized_query, *self.expanded_terms))


def normalize_query(query: str) -> NormalizedQuery:
    normalized = normalize_german_text(query).casefold()
    expanded: list[str] = []
    for stem, terms in GERMAN_EXPANSIONS.items():
        if stem in normalized:
            expanded.extend(terms)
    identifiers = {
        match.group(0).replace(" ", "")
        for pattern in IDENTIFIER_PATTERNS
        for match in pattern.finditer(query)
    }
    return NormalizedQuery(
        original_query=query,
        normalized_query=normalized,
        expanded_terms=tuple(dict.fromkeys(expanded)),
        exact_identifiers=tuple(sorted(identifiers)),
    )
