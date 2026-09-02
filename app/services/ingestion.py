from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from app.domain.banking import GermanBankStatementParser
from app.domain.german import parse_account_folder
from app.domain.models import BankTransaction, DocumentChunk, ProcessingStatus, SourceDocument
from app.integrations.embeddings import EmbeddingProvider
from app.integrations.google_drive import DocumentSource
from app.integrations.pinecone import build_vector_metadata
from app.parsers.registry import ParserRegistry
from app.rag.chunking import DocumentChunker
from app.services.audit import AuditSink, NullAuditSink
from app.services.classification import classify_document
from app.services.hashing import binary_sha256, normalized_text_sha256


@dataclass(frozen=True, slots=True)
class StagedVersion:
    document_id: UUID
    version_id: str
    previous_version_id: str | None
    unchanged: bool = False


class IngestionStore(Protocol):
    async def find_duplicate(
        self, *, tenant_id: UUID, source_id: str, binary_hash: str, text_hash: str
    ) -> tuple[UUID, str] | None: ...

    async def stage(
        self,
        *,
        tenant_id: UUID,
        source: SourceDocument,
        document_id: UUID,
        document_type: str,
        parsed: Any,
        chunks: list[DocumentChunk],
        transactions: list[BankTransaction],
        binary_hash: str,
        text_hash: str,
        embedding_model: str,
        embedding_dimension: int,
        duplicate: tuple[UUID, str] | None = None,
    ) -> StagedVersion: ...

    async def activate(self, staged: StagedVersion) -> None: ...

    async def fail(self, staged: StagedVersion, *, status: str, error: str) -> None: ...

    async def mark_deleted(self, *, tenant_id: UUID, source_id: str) -> str | None: ...


class VectorStore(Protocol):
    async def upsert(
        self,
        vectors: list[tuple[str, list[float], dict[str, Any]]],
        *,
        tenant_id: str,
    ) -> None: ...

    async def delete_version(self, *, tenant_id: str, document_version_id: str) -> None: ...


@dataclass(slots=True)
class SyncCounters:
    discovered: int = 0
    processed: int = 0
    skipped: int = 0
    updated: int = 0
    failed: int = 0
    requires_ocr: int = 0
    vectors_created: int = 0
    errors: list[str] = field(default_factory=list)


class IngestionService:
    def __init__(
        self,
        *,
        source: DocumentSource,
        parsers: ParserRegistry,
        chunker: DocumentChunker,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
        store: IngestionStore,
        embedding_model: str,
        max_file_size_bytes: int = 100 * 1024 * 1024,
        audit: AuditSink | None = None,
    ) -> None:
        self.source = source
        self.parsers = parsers
        self.chunker = chunker
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.store = store
        self.embedding_model = embedding_model
        self.max_file_size_bytes = max_file_size_bytes
        self.audit = audit or NullAuditSink()
        self.bank_parser = GermanBankStatementParser()
        self._last_vectors_created = 0

    async def sync(
        self, *, tenant_id: UUID, limit: int | None = None, dry_run: bool = True
    ) -> SyncCounters:
        counters = SyncCounters()
        async for document in self.source.list_documents(limit=limit):
            counters.discovered += 1
            try:
                outcome = await self.process_document(
                    document, tenant_id=tenant_id, dry_run=dry_run
                )
                if outcome == ProcessingStatus.REQUIRES_OCR:
                    counters.requires_ocr += 1
                elif outcome == ProcessingStatus.READY:
                    counters.processed += 1
                    counters.vectors_created += self._last_vectors_created
                else:
                    counters.skipped += 1
            except Exception as exc:  # individual files must not abort a resumable sync
                counters.failed += 1
                counters.errors.append(f"{document.folder_path}/{document.name}: {exc}")
        return counters

    async def sync_changes(
        self, *, tenant_id: UUID, page_token: str, dry_run: bool = True
    ) -> tuple[SyncCounters, str]:
        counters = SyncCounters()
        changes, next_token = await self.source.get_changes(page_token)
        for change in changes:
            counters.discovered += 1
            try:
                if change.removed:
                    if not dry_run:
                        version_id = await self.store.mark_deleted(
                            tenant_id=tenant_id, source_id=change.file_id
                        )
                        if version_id:
                            await self.vector_store.delete_version(
                                tenant_id=str(tenant_id), document_version_id=version_id
                            )
                    counters.updated += 1
                elif change.document is not None:
                    await self.process_document(
                        change.document, tenant_id=tenant_id, dry_run=dry_run
                    )
                    counters.updated += 1
            except Exception as exc:
                counters.failed += 1
                counters.errors.append(f"Drive change {change.file_id}: {exc}")
        return counters, next_token

    async def process_document(
        self, source: SourceDocument, *, tenant_id: UUID, dry_run: bool
    ) -> ProcessingStatus:
        self._last_vectors_created = 0
        correlation_id = str(uuid4())
        if source.size is not None and source.size > self.max_file_size_bytes:
            raise ValueError(f"File is larger than configured limit: {source.name}")
        parser = self.parsers.get(source.mime_type)
        content = await self.source.download(source)
        await self.audit.record(
            tenant_id=tenant_id,
            event_type="file_downloaded",
            entity_type="drive_file",
            entity_id=source.source_id,
            correlation_id=correlation_id,
            metadata={
                "file_name": source.name,
                "folder_path": source.folder_path,
                "mime_type": source.mime_type,
            },
        )
        if len(content) > self.max_file_size_bytes:
            raise ValueError(f"Downloaded file is larger than configured limit: {source.name}")
        parsed = await parser.parse(content, file_name=source.name)
        await self.audit.record(
            tenant_id=tenant_id,
            event_type=(
                "ocr_required"
                if parsed.status == ProcessingStatus.REQUIRES_OCR
                else "parse_completed"
            ),
            entity_type="drive_file",
            entity_id=source.source_id,
            correlation_id=correlation_id,
            metadata={"status": parsed.status.value, "parser_version": parsed.parser_version},
        )
        document_id = uuid5(NAMESPACE_URL, f"{tenant_id}:{source.source_id}")
        file_hash = binary_sha256(content)
        text_hash = normalized_text_sha256(parsed.normalized_text)
        document_type = classify_document(
            file_name=source.name,
            folder_path=source.folder_path,
            text=parsed.normalized_text,
        )
        version = source.checksum or file_hash
        chunks: list[DocumentChunk] = []
        transactions: list[BankTransaction] = []
        if parsed.status == ProcessingStatus.READY:
            if document_type.value == "bank_statement":
                transactions = self.bank_parser.parse(parsed.normalized_text)
                chunks = self.chunker.chunk_transactions(
                    transactions,
                    statement_header=source.name,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    document_version=version,
                    parser_version=parsed.parser_version,
                )
            if not chunks:
                chunks = self.chunker.chunk(
                    parsed,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    document_version=version,
                )
        if dry_run:
            return parsed.status
        duplicate = await self.store.find_duplicate(
            tenant_id=tenant_id,
            source_id=source.source_id,
            binary_hash=file_hash,
            text_hash=text_hash,
        )
        staged = await self.store.stage(
            tenant_id=tenant_id,
            source=source,
            document_id=document_id,
            document_type=document_type.value,
            parsed=parsed,
            chunks=[] if duplicate else chunks,
            transactions=[] if duplicate else transactions,
            binary_hash=file_hash,
            text_hash=text_hash,
            embedding_model=self.embedding_model,
            embedding_dimension=self.embeddings.dimension,
            duplicate=duplicate,
        )
        if staged.unchanged:
            return ProcessingStatus.SKIPPED
        if parsed.status != ProcessingStatus.READY:
            await self.store.fail(
                staged, status=parsed.status.value, error="; ".join(parsed.warnings)
            )
            return parsed.status
        if duplicate:
            await self.store.activate(staged)
            return ProcessingStatus.READY
        vectors = await self.embeddings.embed_documents([chunk.text for chunk in chunks])
        payload = [
            (
                chunk.chunk_id,
                vector,
                build_vector_metadata(
                    chunk,
                    tenant_id=str(tenant_id),
                    file_name=source.name,
                    drive_file_id=source.source_id,
                    folder_path=source.folder_path,
                    document_type=document_type.value,
                    extra=self._source_metadata(source),
                ),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            if payload:
                await self.vector_store.upsert(payload, tenant_id=str(tenant_id))
                self._last_vectors_created = len(payload)
                await self.audit.record(
                    tenant_id=tenant_id,
                    event_type="pinecone_upsert",
                    entity_type="document_version",
                    entity_id=staged.version_id,
                    correlation_id=correlation_id,
                    metadata={"count": len(payload)},
                )
            await self.store.activate(staged)
        except Exception as exc:
            await self.store.fail(staged, status="failed", error=str(exc))
            raise
        if staged.previous_version_id:
            await self.vector_store.delete_version(
                tenant_id=str(tenant_id), document_version_id=staged.previous_version_id
            )
        return ProcessingStatus.READY

    @staticmethod
    def _source_metadata(
        source: SourceDocument,
    ) -> dict[str, str | int | float | bool | None]:
        folder = parse_account_folder(source.folder_path)
        years = re.findall(r"(?:^|[/\\])((?:19|20)\d{2})(?:[/\\]|$)", source.folder_path)
        return {
            "tax_year": int(years[-1]) if years else None,
            "jurisdiction": "DE",
            "account_label": folder.account_label,
            "currency": folder.expected_currency,
        }


class FakeDocumentSource:
    def __init__(self, documents: list[tuple[SourceDocument, bytes]]) -> None:
        self.documents = documents
        self._content = {document.source_id: content for document, content in documents}

    def list_documents(self, *, limit: int | None = None) -> AsyncIterator[SourceDocument]:
        async def iterator() -> AsyncIterator[SourceDocument]:
            for document, _ in self.documents[:limit]:
                yield document

        return iterator()

    async def download(self, document: SourceDocument) -> bytes:
        return self._content[document.source_id]

    async def get_metadata(self, source_id: str) -> SourceDocument:
        return next(document for document, _ in self.documents if document.source_id == source_id)

    async def get_changes(self, page_token: str) -> tuple[list[Any], str]:
        return [], page_token


class InMemoryIngestionStore:
    def __init__(self) -> None:
        self.versions: dict[str, dict[str, Any]] = {}
        self.active: dict[UUID, str] = {}

    async def find_duplicate(
        self, *, tenant_id: UUID, source_id: str, binary_hash: str, text_hash: str
    ) -> tuple[UUID, str] | None:
        for value in self.versions.values():
            if value["tenant_id"] != tenant_id or value["source"].source_id == source_id:
                continue
            if value["binary_hash"] == binary_hash:
                return value["document_id"], "exact_duplicate"
            if value["text_hash"] == text_hash:
                return value["document_id"], "content_duplicate"
        return None

    async def stage(self, **kwargs: Any) -> StagedVersion:
        document_id: UUID = kwargs["document_id"]
        version_id = str(uuid5(NAMESPACE_URL, f"{document_id}:{kwargs['binary_hash']}"))
        active_version_id = self.active.get(document_id)
        if active_version_id is not None:
            active_version = self.versions.get(active_version_id)
            if (
                active_version is not None
                and active_version["text_hash"] == kwargs["text_hash"]
                and active_version["parsed"].parser_version == kwargs["parsed"].parser_version
            ):
                return StagedVersion(
                    document_id,
                    active_version_id,
                    active_version_id,
                    unchanged=True,
                )
        unchanged = version_id in self.versions and self.active.get(document_id) == version_id
        if version_id not in self.versions:
            self.versions[version_id] = kwargs
        return StagedVersion(
            document_id,
            version_id,
            self.active.get(document_id),
            unchanged=unchanged,
        )

    async def activate(self, staged: StagedVersion) -> None:
        self.active[staged.document_id] = staged.version_id
        self.versions[staged.version_id]["status"] = "ready"

    async def fail(self, staged: StagedVersion, *, status: str, error: str) -> None:
        self.versions[staged.version_id]["status"] = status
        self.versions[staged.version_id]["error"] = error

    async def mark_deleted(self, *, tenant_id: UUID, source_id: str) -> str | None:
        for version_id, value in self.versions.items():
            if value["tenant_id"] == tenant_id and value["source"].source_id == source_id:
                document_id = value["document_id"]
                self.active.pop(document_id, None)
                value["status"] = "deleted"
                return version_id
        return None


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.vectors: dict[str, tuple[list[float], dict[str, Any]]] = {}

    async def upsert(
        self,
        vectors: list[tuple[str, list[float], dict[str, Any]]],
        *,
        tenant_id: str,
    ) -> None:
        self.vectors.update({item_id: (vector, metadata) for item_id, vector, metadata in vectors})

    async def delete_version(self, *, tenant_id: str, document_version_id: str) -> None:
        self.vectors = {
            key: value
            for key, value in self.vectors.items()
            if value[1].get("document_version_id") != document_version_id
        }
