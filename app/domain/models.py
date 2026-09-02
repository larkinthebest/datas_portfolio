from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    BANK_STATEMENT = "bank_statement"
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"
    RECEIPT = "receipt"
    PAYMENT_CONFIRMATION = "payment_confirmation"
    CONTRACT = "contract"
    LOAN_DOCUMENT = "loan_document"
    UTILITY_BILL = "utility_bill"
    PROPERTY_DOCUMENT = "property_document"
    TAX_DOCUMENT = "tax_document"
    PAYROLL_DOCUMENT = "payroll_document"
    INSURANCE_DOCUMENT = "insurance_document"
    LEGAL_DOCUMENT = "legal_document"
    SPREADSHEET_REGISTER = "spreadsheet_register"
    CORRESPONDENCE = "correspondence"
    REFERENCE_DOCUMENT = "reference_document"
    UNKNOWN = "unknown"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    SKIPPED = "skipped"
    REQUIRES_OCR = "requires_ocr"
    FAILED = "failed"
    DELETED = "deleted"


class MoneyDirection(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"
    UNKNOWN = "unknown"


class SourceAnchor(BaseModel):
    document_id: UUID | None = None
    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    column: str | None = None
    section: str | None = None
    text_fragment: str = ""


class ExtractedValue(BaseModel):
    raw_value: str
    normalized_value: str | None
    confidence: float = Field(ge=0, le=1)
    source_anchor: SourceAnchor
    manual_override: str | None = None


class ParsedMoney(BaseModel):
    raw_amount: str
    normalized_amount: Decimal
    currency: str | None = None
    direction: MoneyDirection
    confidence: float = Field(default=1.0, ge=0, le=1)
    is_percentage: bool = False


class ParsedPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str
    tables: list[list[list[str]]] = Field(default_factory=list)
    char_count: int = Field(ge=0)
    has_text_layer: bool


class SpreadsheetRow(BaseModel):
    sheet_name: str
    row_number: int = Field(ge=1)
    column_headers: list[str]
    values: list[str]


class ParsedDocument(BaseModel):
    pages: list[ParsedPage] = Field(default_factory=list)
    rows: list[SpreadsheetRow] = Field(default_factory=list)
    original_text: str = ""
    normalized_text: str = ""
    status: ProcessingStatus = ProcessingStatus.READY
    parser_version: str
    warnings: list[str] = Field(default_factory=list)


class SourceDocument(BaseModel):
    source_id: str
    name: str
    mime_type: str
    source_mime_type: str | None = None
    folder_path: str
    size: int | None = None
    modified_time: datetime | None = None
    checksum: str | None = None
    web_url: str | None = None
    parent_ids: list[str] = Field(default_factory=list)


class AccountFolderMetadata(BaseModel):
    account_label: str | None = None
    account_code: str | None = None
    account_role: str | None = None
    expected_currency: str | None = None
    folder_path: str


class BankTransaction(BaseModel):
    account_id: UUID | None = None
    statement_document_id: UUID | None = None
    statement_page: int | None = None
    booking_date: date
    value_date: date | None = None
    amount: Decimal
    currency: str
    direction: MoneyDirection
    counterparty: str | None = None
    iban: str | None = None
    bic: str | None = None
    reference: str | None = None
    booking_text: str | None = None
    end_to_end_reference: str | None = None
    mandate_reference: str | None = None
    creditor_id: str | None = None
    raw_text: str
    extraction_confidence: float = Field(default=1.0, ge=0, le=1)


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: UUID
    document_version: str
    chunk_index: int = Field(ge=0)
    text: str
    content_hash: str
    page: int | None = None
    sheet: str | None = None
    row_from: int | None = None
    row_to: int | None = None
    section: str | None = None
    parser_version: str
    chunker_version: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RetrievalHit(BaseModel):
    chunk_id: str
    score: float
    source: str
    text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnswerSource(BaseModel):
    document_id: UUID | None = None
    file_name: str
    drive_url: str | None = None
    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    chunk_id: str
    quote: str
    relevance_score: float


class RagAnswer(BaseModel):
    answer: str
    confidence: float = Field(ge=0, le=1)
    sources: list[AnswerSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
