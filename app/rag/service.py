from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.domain.models import RagAnswer, RetrievalHit
from app.integrations.gemini import GeminiProvider
from app.rag.retrieval import HybridRetriever


class ChunkHydrator(Protocol):
    async def get_many(
        self, chunk_ids: Sequence[str], *, tenant_id: UUID
    ) -> list[RetrievalHit]: ...


class RagService:
    def __init__(
        self,
        *,
        retriever: HybridRetriever,
        chunks: ChunkHydrator,
        generator: GeminiProvider,
    ) -> None:
        self.retriever = retriever
        self.chunks = chunks
        self.generator = generator

    async def ask(self, query: str, *, tenant_id: UUID) -> RagAnswer:
        _, hits = await self.retriever.search(query, tenant_id=str(tenant_id))
        if not hits:
            return RagAnswer(
                answer="Недостаточно данных для подтверждённого ответа.",
                confidence=0,
                missing_information=["Подходящие документы не найдены"],
            )
        hydrated = await self.chunks.get_many([hit.chunk_id for hit in hits], tenant_id=tenant_id)
        by_id = {hit.chunk_id: hit for hit in hydrated}
        evidence = [
            by_id[hit.chunk_id].model_copy(update={"score": hit.score, "source": hit.source})
            for hit in hits
            if hit.chunk_id in by_id
        ]
        return await self.generator.answer(query, evidence)
