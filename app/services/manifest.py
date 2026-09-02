from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class IndexManifest(BaseModel):
    embedding_model: str
    embedding_dimension: int
    chunker_version: str
    parser_versions: dict[str, str]
    normalizer_version: str = "german_normalizer:v1"
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_documents: int
    total_chunks: int

    def assert_compatible(self, *, embedding_model: str, embedding_dimension: int) -> None:
        if (
            self.embedding_model != embedding_model
            or self.embedding_dimension != embedding_dimension
        ):
            raise ValueError("Embedding configuration changed; a controlled reindex is required")
