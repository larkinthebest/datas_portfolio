from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class BankAccount(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "bank_accounts"
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    account_code: Mapped[str | None] = mapped_column(String(100), index=True)
    account_role: Mapped[str | None] = mapped_column(String(50))
    iban: Mapped[str | None] = mapped_column(String(64), index=True)
    bic: Mapped[str | None] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    folder_path: Mapped[str | None] = mapped_column(Text)


class BankTransaction(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "bank_transactions"
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("bank_accounts.id"), nullable=False, index=True
    )
    statement_document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    statement_page: Mapped[int | None] = mapped_column(Integer)
    booking_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    value_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    counterparty: Mapped[str | None] = mapped_column(String(1000), index=True)
    iban: Mapped[str | None] = mapped_column(String(64), index=True)
    bic: Mapped[str | None] = mapped_column(String(32))
    reference: Mapped[str | None] = mapped_column(Text, index=True)
    booking_text: Mapped[str | None] = mapped_column(Text)
    end_to_end_reference: Mapped[str | None] = mapped_column(String(500), index=True)
    mandate_reference: Mapped[str | None] = mapped_column(String(500), index=True)
    creditor_id: Mapped[str | None] = mapped_column(String(500))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)


class ReconciliationCandidate(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "reconciliation_candidates"
    transaction_id: Mapped[UUID] = mapped_column(ForeignKey("bank_transactions.id"), nullable=False)
    financial_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("financial_documents.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    component_scores: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    conflicts: Mapped[list[str]] = mapped_column(JSON, default=list)


class ReconciliationMatch(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "reconciliation_matches"
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("reconciliation_candidates.id"), nullable=False
    )
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[UUID | None] = mapped_column(nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Calculation(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "calculations"
    kind: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    intermediate_steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    rounding_rule: Mapped[str] = mapped_column(String(100), nullable=False)
    legal_rule_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("legal_rule_versions.id"))
    created_by: Mapped[UUID | None] = mapped_column(nullable=True)


class CalculationInput(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "calculation_inputs"
    calculation_id: Mapped[UUID] = mapped_column(ForeignKey("calculations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id"))


class CalculationResult(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "calculation_results"
    calculation_id: Mapped[UUID] = mapped_column(ForeignKey("calculations.id"), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    output: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class LegalRule(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "legal_rules"
    jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(2), default="DE")
    state: Mapped[str | None] = mapped_column(String(100))
    rule_code: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")


class LegalRuleVersion(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "legal_rule_versions"
    legal_rule_id: Mapped[UUID] = mapped_column(ForeignKey("legal_rules.id"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    tax_year: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id"))
    review_status: Mapped[str] = mapped_column(String(50), default="draft")
    reviewed_by: Mapped[UUID | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class DeclarationField(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "declaration_fields"
    field_code: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)


class DeclarationValue(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "declaration_values"
    declaration_field_id: Mapped[UUID] = mapped_column(
        ForeignKey("declaration_fields.id"), nullable=False
    )
    value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    calculation_id: Mapped[UUID] = mapped_column(ForeignKey("calculations.id"), nullable=False)
    included_records: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_records: Mapped[list[str]] = mapped_column(JSON, default=list)
    sources: Mapped[list[object]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
