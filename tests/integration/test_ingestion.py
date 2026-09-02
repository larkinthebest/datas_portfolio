from uuid import UUID

import pytest

from app.domain.models import ProcessingStatus, SourceDocument
from app.integrations.embeddings import FakeEmbeddingProvider
from app.parsers.registry import ParserRegistry
from app.parsers.text import TextParser
from app.rag.chunking import DocumentChunker
from app.services.ingestion import (
    FakeDocumentSource,
    IngestionService,
    InMemoryIngestionStore,
    InMemoryVectorStore,
)

TENANT = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_fake_drive_to_chunks_and_vectors_is_idempotent() -> None:
    document = SourceDocument(
        source_id="drive-1",
        name="Heizkostenabrechnung_2025.txt",
        mime_type="text/plain",
        folder_path="Allgemeine_Kosten/2025",
    )
    source = FakeDocumentSource([(document, b"Die Heizkosten betragen 940,00 EUR.")])
    store = InMemoryIngestionStore()
    vectors = InMemoryVectorStore()
    service = IngestionService(
        source=source,
        parsers=ParserRegistry([TextParser()]),
        chunker=DocumentChunker(target_words=20, overlap_words=2),
        embeddings=FakeEmbeddingProvider(16),
        vector_store=vectors,
        store=store,
        embedding_model="fake",
    )
    first = await service.process_document(document, tenant_id=TENANT, dry_run=False)
    vector_ids = set(vectors.vectors)
    # Native Google exports may change binary bytes while parsed text stays identical.
    source._content[document.source_id] += b"\n"
    second = await service.process_document(document, tenant_id=TENANT, dry_run=False)
    assert first == ProcessingStatus.READY
    assert second == ProcessingStatus.SKIPPED
    assert service._last_vectors_created == 0
    assert set(vectors.vectors) == vector_ids
    assert len(store.active) == 1


@pytest.mark.asyncio
async def test_dry_run_has_no_external_writes() -> None:
    document = SourceDocument(
        source_id="drive-2",
        name="note.txt",
        mime_type="text/plain",
        folder_path="Steuern/2025",
    )
    source = FakeDocumentSource([(document, b"Grundsteuer 168,88 EUR")])
    store = InMemoryIngestionStore()
    vectors = InMemoryVectorStore()
    service = IngestionService(
        source=source,
        parsers=ParserRegistry([TextParser()]),
        chunker=DocumentChunker(target_words=20, overlap_words=2),
        embeddings=FakeEmbeddingProvider(16),
        vector_store=vectors,
        store=store,
        embedding_model="fake",
    )
    result = await service.sync(tenant_id=TENANT, limit=20, dry_run=True)
    assert result.processed == 1
    assert store.versions == {}
    assert vectors.vectors == {}


@pytest.mark.asyncio
async def test_bank_ingestion_stages_structured_transactions() -> None:
    document = SourceDocument(
        source_id="bank-1",
        name="Kontoauszug Dezember 2025.txt",
        mime_type="text/plain",
        folder_path="Bank/713600_Ausgaben/2025",
    )
    content = b"""Kontoauszug\nKontow\xc3\xa4hrung: EUR\nBuchungsdatum: 01.12.2025\nWEG Beispiel 41\n299,85-\nEnd-to-End-Ref.: TEST123"""
    store = InMemoryIngestionStore()
    service = IngestionService(
        source=FakeDocumentSource([(document, content)]),
        parsers=ParserRegistry([TextParser()]),
        chunker=DocumentChunker(target_words=30, overlap_words=2),
        embeddings=FakeEmbeddingProvider(16),
        vector_store=InMemoryVectorStore(),
        store=store,
        embedding_model="fake",
    )
    await service.process_document(document, tenant_id=TENANT, dry_run=False)
    staged = next(iter(store.versions.values()))
    assert len(staged["transactions"]) == 1
    assert staged["transactions"][0].end_to_end_reference == "TEST123"
