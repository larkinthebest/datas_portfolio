from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain.models import RetrievalHit
from app.rag.query import NormalizedQuery, normalize_query


class SemanticRetriever(Protocol):
    async def search(self, query: str, *, tenant_id: str, top_k: int) -> list[RetrievalHit]: ...


class LexicalRetriever(Protocol):
    async def search(self, query: str, *, tenant_id: str, top_k: int) -> list[RetrievalHit]: ...


class ExactRetriever(Protocol):
    async def search_exact(
        self, identifiers: Sequence[str], *, tenant_id: str, top_k: int
    ) -> list[RetrievalHit]: ...


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[RetrievalHit]], *, constant: int = 60
) -> list[RetrievalHit]:
    scores: dict[str, float] = {}
    best: dict[str, RetrievalHit] = {}
    sources: dict[str, set[str]] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (constant + rank)
            if hit.chunk_id not in best or hit.score > best[hit.chunk_id].score:
                best[hit.chunk_id] = hit
            sources.setdefault(hit.chunk_id, set()).add(hit.source)
    return [
        best[chunk_id].model_copy(
            update={"score": score, "source": "+".join(sorted(sources[chunk_id]))}
        )
        for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


class HybridRetriever:
    def __init__(
        self,
        semantic: SemanticRetriever,
        lexical: LexicalRetriever,
        exact: ExactRetriever,
        *,
        semantic_k: int = 20,
        lexical_k: int = 20,
        final_k: int = 8,
    ) -> None:
        self.semantic = semantic
        self.lexical = lexical
        self.exact = exact
        self.semantic_k = semantic_k
        self.lexical_k = lexical_k
        self.final_k = final_k

    async def search(
        self, query: str, *, tenant_id: str
    ) -> tuple[NormalizedQuery, list[RetrievalHit]]:
        normalized = normalize_query(query)
        semantic_hits = await self.semantic.search(
            normalized.search_text, tenant_id=tenant_id, top_k=self.semantic_k
        )
        lexical_hits = await self.lexical.search(
            normalized.search_text, tenant_id=tenant_id, top_k=self.lexical_k
        )
        exact_hits = (
            await self.exact.search_exact(
                normalized.exact_identifiers, tenant_id=tenant_id, top_k=self.final_k
            )
            if normalized.exact_identifiers
            else []
        )
        fused = reciprocal_rank_fusion([exact_hits, lexical_hits, semantic_hits])
        return normalized, fused[: self.final_k]
