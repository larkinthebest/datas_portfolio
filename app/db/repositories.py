from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk
from app.domain.models import RetrievalHit


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_many(self, chunk_ids: Sequence[str], *, tenant_id: UUID) -> list[RetrievalHit]:
        if not chunk_ids:
            return []
        rows = (
            await self.session.scalars(
                select(DocumentChunk).where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.active.is_(True),
                    DocumentChunk.chunk_id.in_(chunk_ids),
                )
            )
        ).all()
        by_id = {row.chunk_id: row for row in rows}
        return [
            self._to_hit(by_id[item], score=0, source="hydrate")
            for item in chunk_ids
            if item in by_id
        ]

    async def search(self, query: str, *, tenant_id: str, top_k: int) -> list[RetrievalHit]:
        tenant_uuid = UUID(tenant_id)
        dialect = self.session.bind.dialect.name if self.session.bind is not None else ""
        if dialect == "postgresql":
            vector = func.to_tsvector("german", DocumentChunk.normalized_text)
            ts_query = func.websearch_to_tsquery("german", query)
            rank = func.ts_rank_cd(vector, ts_query)
            statement: Select[tuple[DocumentChunk, float]] = (
                select(DocumentChunk, rank.label("rank"))
                .where(
                    DocumentChunk.tenant_id == tenant_uuid,
                    DocumentChunk.active.is_(True),
                    vector.op("@@")(ts_query),
                )
                .order_by(rank.desc())
                .limit(top_k)
            )
            postgres_rows = (await self.session.execute(statement)).all()
            return [
                self._to_hit(row, float(rank_value), "lexical") for row, rank_value in postgres_rows
            ]
        terms = [term for term in query.split() if len(term) > 2][:8]
        conditions = [DocumentChunk.normalized_text.ilike(f"%{term}%") for term in terms]
        if not conditions:
            return []
        fallback_rows = (
            await self.session.scalars(
                select(DocumentChunk)
                .where(
                    DocumentChunk.tenant_id == tenant_uuid,
                    DocumentChunk.active.is_(True),
                    or_(*conditions),
                )
                .limit(top_k)
            )
        ).all()
        return [
            self._to_hit(row, 1.0 / (index + 1), "lexical")
            for index, row in enumerate(fallback_rows)
        ]

    async def search_exact(
        self, identifiers: Sequence[str], *, tenant_id: str, top_k: int
    ) -> list[RetrievalHit]:
        if not identifiers:
            return []
        conditions = [
            or_(
                DocumentChunk.normalized_text.ilike(f"%{value}%"),
                func.replace(DocumentChunk.normalized_text, " ", "").ilike(f"%{value}%"),
            )
            for value in identifiers
        ]
        rows = (
            await self.session.scalars(
                select(DocumentChunk)
                .where(
                    DocumentChunk.tenant_id == UUID(tenant_id),
                    DocumentChunk.active.is_(True),
                    or_(*conditions),
                )
                .limit(top_k)
            )
        ).all()
        return [self._to_hit(row, 1.0, "exact") for row in rows]

    @staticmethod
    def _to_hit(row: DocumentChunk, score: float, source: str) -> RetrievalHit:
        return RetrievalHit(
            chunk_id=row.chunk_id,
            score=score,
            source=source,
            text=row.original_text,
            metadata={
                **row.metadata_json,
                "document_id": str(row.document_id),
                "page": row.page,
                "sheet": row.sheet,
            },
        )
