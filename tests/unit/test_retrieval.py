from collections.abc import Sequence

import pytest

from app.domain.models import RetrievalHit
from app.rag.query import normalize_query
from app.rag.retrieval import HybridRetriever, reciprocal_rank_fusion


def test_russian_query_expands_to_german_compounds() -> None:
    query = normalize_query("Сколько составили расходы на отопление за 2025 год?")
    assert "Heizkosten" in query.expanded_terms
    assert "Heizkostenabrechnung" in query.expanded_terms


def test_exact_identifier_extraction() -> None:
    query = normalize_query("Найди операцию с End-to-End-Ref TEST123")
    assert "TEST123" in query.exact_identifiers


def test_rrf_deduplicates_and_rewards_multiple_rankings() -> None:
    semantic = [
        RetrievalHit(chunk_id="a", score=0.9, source="semantic"),
        RetrievalHit(chunk_id="b", score=0.8, source="semantic"),
    ]
    lexical = [RetrievalHit(chunk_id="b", score=1, source="lexical")]
    fused = reciprocal_rank_fusion([semantic, lexical])
    assert fused[0].chunk_id == "b"
    assert fused[0].source == "lexical+semantic"


class _Retriever:
    def __init__(self, source: str) -> None:
        self.source = source
        self.last_query = ""

    async def search(self, query: str, *, tenant_id: str, top_k: int) -> list[RetrievalHit]:
        self.last_query = query
        return [RetrievalHit(chunk_id="heat", score=1, source=self.source)]

    async def search_exact(
        self, identifiers: Sequence[str], *, tenant_id: str, top_k: int
    ) -> list[RetrievalHit]:
        return []


@pytest.mark.asyncio
async def test_hybrid_retrieval_uses_expanded_query() -> None:
    semantic = _Retriever("semantic")
    lexical = _Retriever("lexical")
    hybrid = HybridRetriever(semantic, lexical, lexical)
    _, hits = await hybrid.search("расходы на отопление", tenant_id="tenant")
    assert "Heizkosten" in semantic.last_query
    assert hits[0].chunk_id == "heat"
