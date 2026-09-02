from __future__ import annotations

from app.domain.models import RetrievalHit
from app.integrations.embeddings import EmbeddingProvider
from app.integrations.pinecone import PineconeVectorStore


class PineconeSemanticRetriever:
    def __init__(self, embeddings: EmbeddingProvider, vector_store: PineconeVectorStore) -> None:
        self.embeddings = embeddings
        self.vector_store = vector_store

    async def search(self, query: str, *, tenant_id: str, top_k: int) -> list[RetrievalHit]:
        vector = await self.embeddings.embed_query(query)
        return await self.vector_store.query(vector, tenant_id=tenant_id, top_k=top_k)
