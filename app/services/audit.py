from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditEvent

SAFE_METADATA_KEYS = frozenset(
    {"file_name", "folder_path", "mime_type", "status", "count", "parser_version"}
)


class AuditSink(Protocol):
    async def record(
        self,
        *,
        tenant_id: UUID,
        event_type: str,
        entity_type: str,
        entity_id: str | None,
        correlation_id: str,
        metadata: dict[str, object] | None = None,
    ) -> None: ...


class NullAuditSink:
    async def record(
        self,
        *,
        tenant_id: UUID,
        event_type: str,
        entity_type: str,
        entity_id: str | None,
        correlation_id: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        return None


class SQLAlchemyAuditSink:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def record(
        self,
        *,
        tenant_id: UUID,
        event_type: str,
        entity_type: str,
        entity_id: str | None,
        correlation_id: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        safe_metadata = {
            key: value for key, value in (metadata or {}).items() if key in SAFE_METADATA_KEYS
        }
        async with self.factory() as session, session.begin():
            session.add(
                AuditEvent(
                    tenant_id=tenant_id,
                    timestamp=datetime.now(UTC),
                    event_type=event_type,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    correlation_id=correlation_id,
                    metadata_json=safe_metadata,
                )
            )
