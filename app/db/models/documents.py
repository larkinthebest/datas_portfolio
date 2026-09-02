from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DataSource(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "data_sources"
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class DriveFolder(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "drive_folders"
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    drive_folder_id: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_drive_folder_id: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    logical_path: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "drive_folder_id"),)


class DriveFile(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "drive_files"
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    drive_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    folder_path: Mapped[str] = mapped_column(Text, nullable=False)
    web_url: Mapped[str | None] = mapped_column(Text)
    drive_created_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    drive_modified_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    size: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(String(128))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("tenant_id", "drive_file_id"),)


class Document(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "documents"
    drive_file_id: Mapped[UUID] = mapped_column(ForeignKey("drive_files.id"), nullable=False)
    active_version_id: Mapped[UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    document_type: Mapped[str] = mapped_column(String(100), default="unknown", index=True)
    original_document_type: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(10), default="de")
    duplicate_of_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id"))
    duplicate_kind: Mapped[str | None] = mapped_column(String(50))


class DocumentVersion(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "document_versions"
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False, index=True
    )
    drive_revision: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    text_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    original_text: Mapped[str] = mapped_column(Text, default="")
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentPage(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "document_pages"
    document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, default="")
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    has_text_layer: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("document_version_id", "page_number"),)


class DocumentChunk(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "document_chunks"
    chunk_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False, index=True
    )
    document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page: Mapped[int | None] = mapped_column(Integer)
    sheet: Mapped[str | None] = mapped_column(String(255))
    row_from: Mapped[int | None] = mapped_column(Integer)
    row_to: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        Index(
            "ix_document_chunks_fts_de",
            text("to_tsvector('german', normalized_text)"),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_document_chunks_trgm",
            "normalized_text",
            postgresql_using="gin",
            postgresql_ops={"normalized_text": "gin_trgm_ops"},
        ).ddl_if(dialect="postgresql"),
    )


class DocumentTable(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "document_tables"
    document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    page: Mapped[int | None] = mapped_column(Integer)
    structured_data: Mapped[list[object]] = mapped_column(JSON, default=list)


class DocumentSheet(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "document_sheets"
    document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    structured_rows: Mapped[list[object]] = mapped_column(JSON, default=list)


class ExtractedField(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "extracted_fields"
    document_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    source_anchor: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    manual_override: Mapped[str | None] = mapped_column(Text)
    override_user_id: Mapped[UUID | None] = mapped_column(nullable=True)


class FinancialDocument(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "financial_documents"
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False, unique=True
    )
    financial_type: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_number: Mapped[str | None] = mapped_column(String(255), index=True)
    counterparty: Mapped[str | None] = mapped_column(String(1000))
    amount_net: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    amount_gross: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    currency: Mapped[str | None] = mapped_column(String(3))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
