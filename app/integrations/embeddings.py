from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core.config import Settings


class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class EmbeddingCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS embeddings (cache_key TEXT PRIMARY KEY, vector TEXT NOT NULL)"
            )

    def get(self, key: str) -> list[float] | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT vector FROM embeddings WHERE cache_key = ?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, vector: list[float]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO embeddings(cache_key, vector) VALUES (?, ?)",
                (key, json.dumps(vector, separators=(",", ":"))),
            )
            connection.commit()


class LocalQwenEmbeddingProvider:
    def __init__(
        self,
        *,
        model_name: str = "Qwen/Qwen3-Embedding-0.6B",
        dimension: int = 1024,
        device: str = "cpu",
        batch_size: int = 16,
        max_length: int = 8192,
        query_instruction: str = (
            "Instruct: Retrieve German financial evidence for the Russian accounting question\nQuery: "
        ),
        cache: EmbeddingCache | None = None,
    ) -> None:
        self.model_name = model_name
        self._dimension = dimension
        self.device = device
        self.batch_size = batch_size
        self.max_length = max_length
        self.query_instruction = query_instruction
        self.cache = cache
        self._model: Any | None = None

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, kind="document")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([self.query_instruction + text], kind="query"))[0]

    async def _embed(self, texts: list[str], *, kind: str) -> list[list[float]]:
        keys = [self._cache_key(text, kind) for text in texts]
        result: list[list[float] | None] = [
            self.cache.get(key) if self.cache else None for key in keys
        ]
        missing_indexes = [index for index, vector in enumerate(result) if vector is None]
        if missing_indexes:
            missing_texts = [texts[index] for index in missing_indexes]
            vectors = await asyncio.to_thread(self._encode, missing_texts)
            for index, vector in zip(missing_indexes, vectors, strict=True):
                result[index] = vector
                if self.cache:
                    self.cache.put(keys[index], vector)
        return [vector for vector in result if vector is not None]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "Install the embeddings extra: pip install -e '.[embeddings]'"
                ) from exc
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._model.max_seq_length = self.max_length
        array = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
            truncate_dim=self._dimension,
        )
        vectors = [[float(item) for item in vector] for vector in array]
        if any(len(vector) != self._dimension for vector in vectors):
            raise ValueError("Embedding model returned an unexpected dimension")
        return vectors

    def _cache_key(self, text: str, kind: str) -> str:
        material = f"{self.model_name}:{self._dimension}:{kind}:{text}".encode()
        return hashlib.sha256(material).hexdigest()


class HTTPEmbeddingProvider:
    def __init__(self, url: str, *, model: str, dimension: int, api_key: str = "") -> None:
        self.url = url
        self.model = model
        self._dimension = dimension
        self.api_key = api_key

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._request(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._request([text]))[0]

    async def _request(self, texts: list[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.url, json={"model": self.model, "input": texts}, headers=headers
            )
            response.raise_for_status()
        vectors = [item["embedding"] for item in response.json()["data"]]
        if any(len(vector) != self.dimension for vector in vectors):
            raise ValueError("HTTP embedding dimension mismatch")
        return vectors


class FakeEmbeddingProvider:
    def __init__(self, dimension: int = 32) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha512(text.casefold().encode()).digest()
        raw = [float(digest[index % len(digest)] - 127) for index in range(self.dimension)]
        norm = math.sqrt(sum(value * value for value in raw)) or 1.0
        return [value / norm for value in raw]


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "http":
        return HTTPEmbeddingProvider(
            settings.embedding_http_url,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            api_key=settings.embedding_http_api_key.get_secret_value(),
        )
    if settings.embedding_provider == "fake":
        return FakeEmbeddingProvider(settings.embedding_dimension)
    return LocalQwenEmbeddingProvider(
        model_name=settings.embedding_model,
        dimension=settings.embedding_dimension,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        max_length=settings.embedding_max_length,
        cache=EmbeddingCache(Path(settings.cache_dir) / "embeddings.sqlite3"),
    )
