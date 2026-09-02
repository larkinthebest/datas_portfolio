from __future__ import annotations

import asyncio
from typing import Any

from app.core.exceptions import ConfigurationError, DimensionMismatchError
from app.domain.models import DocumentChunk, RetrievalHit


def build_vector_metadata(
    chunk: DocumentChunk,
    *,
    tenant_id: str,
    file_name: str,
    drive_file_id: str,
    folder_path: str,
    document_type: str,
    language: str = "de",
    extra: dict[str, str | int | float | bool | None] | None = None,
) -> dict[str, str | int | float | bool]:
    metadata: dict[str, str | int | float | bool] = {
        "tenant_id": tenant_id,
        "document_id": str(chunk.document_id),
        "document_version_id": chunk.document_version,
        "chunk_id": chunk.chunk_id,
        "file_name": file_name,
        "drive_file_id": drive_file_id,
        "folder_path": folder_path,
        "document_type": document_type,
        "language": language,
        "content_hash": chunk.content_hash,
        "parser_version": chunk.parser_version,
        "chunker_version": chunk.chunker_version,
    }
    optional = {"page": chunk.page, "sheet": chunk.sheet, **(extra or {})}
    metadata.update({key: value for key, value in optional.items() if value is not None})
    return metadata


class PineconeVectorStore:
    def __init__(
        self,
        *,
        api_key: str,
        index_name: str,
        expected_dimension: int,
        host: str = "",
        namespace_prefix: str = "ragbot",
    ) -> None:
        if not api_key or not index_name:
            raise ConfigurationError("Pinecone API key and index name are required")
        from pinecone import Pinecone

        self.client = Pinecone(api_key=api_key)
        self.index_name = index_name
        self.expected_dimension = expected_dimension
        self.namespace_prefix = namespace_prefix
        self._host = host
        self._index: Any | None = None

    async def validate_dimension(self) -> None:
        description = await asyncio.to_thread(self.client.describe_index, self.index_name)
        actual = int(description.dimension)
        if actual != self.expected_dimension:
            raise DimensionMismatchError(
                f"Pinecone index dimension is {actual}, embedding provider dimension is "
                f"{self.expected_dimension}. Create a separate compatible index; production index "
                "was not modified."
            )
        self._host = self._host or str(description.host)
        self._index = self.client.Index(host=self._host)

    async def upsert(
        self,
        vectors: list[tuple[str, list[float], dict[str, Any]]],
        *,
        tenant_id: str,
    ) -> None:
        index = self._ready_index()
        if any(len(vector) != self.expected_dimension for _, vector, _ in vectors):
            raise DimensionMismatchError("Attempted to upsert a vector with an invalid dimension")
        await asyncio.to_thread(
            index.upsert,
            vectors=[
                {"id": item_id, "values": vector, "metadata": metadata}
                for item_id, vector, metadata in vectors
            ],
            namespace=self._namespace(tenant_id),
        )

    async def query(
        self,
        vector: list[float],
        *,
        tenant_id: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievalHit]:
        index = self._ready_index()
        response = await asyncio.to_thread(
            index.query,
            vector=vector,
            top_k=top_k,
            namespace=self._namespace(tenant_id),
            filter={**(filters or {}), "tenant_id": tenant_id},
            include_metadata=True,
        )
        return [
            RetrievalHit(
                chunk_id=str(match.metadata["chunk_id"]),
                score=float(match.score),
                source="semantic",
                metadata=dict(match.metadata),
            )
            for match in response.matches
        ]

    async def delete_version(self, *, tenant_id: str, document_version_id: str) -> None:
        index = self._ready_index()
        await asyncio.to_thread(
            index.delete,
            filter={"tenant_id": tenant_id, "document_version_id": document_version_id},
            namespace=self._namespace(tenant_id),
        )

    def _ready_index(self) -> Any:
        if self._index is None:
            raise ConfigurationError("Call validate_dimension before using Pinecone")
        return self._index

    def _namespace(self, tenant_id: str) -> str:
        return f"{self.namespace_prefix}:{tenant_id}"
