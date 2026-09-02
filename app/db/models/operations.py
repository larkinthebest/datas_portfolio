from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(50), default="active")


class User(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "users"
    telegram_user_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="active")
    __table_args__ = (UniqueConstraint("tenant_id", "telegram_user_id"),)


class UserRole(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "user_roles"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "role"),)


class SyncJob(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "sync_jobs"
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    mode: Mapped[str] = mapped_column(String(50), default="incremental")
    dry_run: Mapped[bool] = mapped_column(default=True)
    counters: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    changes_page_token: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessingJob(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "processing_jobs"
    sync_job_id: Mapped[UUID] = mapped_column(ForeignKey("sync_jobs.id"), nullable=False)
    drive_file_id: Mapped[UUID] = mapped_column(ForeignKey("drive_files.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), default="queued")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class RagQuery(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "rag_queries"
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    original_query: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[str] = mapped_column(Text, nullable=False)
    expanded_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    intent: Mapped[str] = mapped_column(String(100), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)


class RagAnswerRecord(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "rag_answer_records"
    rag_query_id: Mapped[UUID] = mapped_column(ForeignKey("rag_queries.id"), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list[object]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    retrieval_confidence: Mapped[str | None] = mapped_column(String(50))
    answer_confidence: Mapped[str | None] = mapped_column(String(50))


class AuditEvent(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "audit_events"
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class IndexManifestRecord(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "index_manifests"
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(100), nullable=False)
    parser_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    normalizer_version: Mapped[str] = mapped_column(String(100), nullable=False)
    total_documents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
