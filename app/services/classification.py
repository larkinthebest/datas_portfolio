from __future__ import annotations

from app.domain.models import DocumentType

_SIGNALS: tuple[tuple[DocumentType, tuple[str, ...]], ...] = (
    (DocumentType.BANK_STATEMENT, ("kontoauszug", "bank/", "buchungsdatum", "kontostand")),
    (DocumentType.CREDIT_NOTE, ("gutschrift", "stornorechnung")),
    (DocumentType.INVOICE, ("rechnung", "rechnungsnummer", "gesamtbetrag")),
    (DocumentType.UTILITY_BILL, ("betriebskosten", "nebenkosten", "heizkosten", "hausgeld")),
    (DocumentType.TAX_DOCUMENT, ("steuerbescheid", "finanzamt", "grundsteuer", "steuernummer")),
    (DocumentType.LOAN_DOCUMENT, ("darlehen", "tilgung", "darlehensvertrag")),
    (DocumentType.CONTRACT, ("vertrag", "vertragsbeginn", "vertragsende")),
    (DocumentType.INSURANCE_DOCUMENT, ("versicherung", "versicherungsbeitrag")),
    (DocumentType.SPREADSHEET_REGISTER, (".xlsx", "tabelle", "register")),
)


def classify_document(*, file_name: str, folder_path: str, text: str) -> DocumentType:
    haystack = f"{folder_path}/{file_name}\n{text[:10000]}".casefold()
    scored = [
        (sum(signal in haystack for signal in signals), document_type)
        for document_type, signals in _SIGNALS
    ]
    score, result = max(scored, key=lambda item: item[0])
    return result if score else DocumentType.UNKNOWN
