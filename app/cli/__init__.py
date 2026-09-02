from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.ingestion import SQLAlchemyIngestionStore
from app.db.models import DataSource, Document, DocumentChunk, IndexManifestRecord, Tenant
from app.db.models.documents import DriveFile
from app.db.session import create_engine, create_session_factory
from app.integrations.embeddings import (
    EmbeddingCache,
    EmbeddingProvider,
    FakeEmbeddingProvider,
    HTTPEmbeddingProvider,
    LocalQwenEmbeddingProvider,
)
from app.integrations.google_drive import GoogleDriveDocumentSource
from app.integrations.ocr import TesseractOCRProvider
from app.integrations.pinecone import PineconeVectorStore
from app.parsers.docx import DocxParser
from app.parsers.pdf import PdfParser
from app.parsers.registry import ParserRegistry
from app.parsers.spreadsheet import SpreadsheetParser
from app.parsers.text import TextParser
from app.rag.chunking import CHUNKER_VERSION, DocumentChunker
from app.services.audit import SQLAlchemyAuditSink
from app.services.capacity import CapacityEstimator
from app.services.ingestion import (
    IngestionService,
    IngestionStore,
    InMemoryIngestionStore,
    InMemoryVectorStore,
    VectorStore,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ragbot", description="German accounting RAG operations")
    subcommands = parser.add_subparsers(dest="command", required=True)
    estimate = subcommands.add_parser(
        "estimate-index", help="Inventory Drive and estimate Pinecone capacity"
    )
    estimate.add_argument(
        "--metadata-only", action="store_true", help="Do not download PDFs to inspect text layers"
    )
    estimate.add_argument("--limit", type=int)
    sync = subcommands.add_parser("sync", help="Run a resumable sample or full Drive sync")
    sync.add_argument("--limit", type=int, default=20)
    sync.add_argument("--full", action="store_true")
    sync.add_argument("--commit", action="store_true", help="Write PostgreSQL and Pinecone")
    sync.add_argument("--confirm", action="store_true", help="Confirm non-dry-run external writes")
    sync.add_argument("--page-token", help="Drive Changes API page token for incremental sync")
    sync.add_argument(
        "--source-id",
        dest="source_ids",
        action="append",
        help="Sync a Google Drive file by ID; repeat for multiple files",
    )
    subcommands.add_parser("verify-index", help="Validate Pinecone dimension without modifying it")
    subcommands.add_parser("drive-token", help="Get the current Drive Changes start token")
    subcommands.add_parser("db-check", help="Check PostgreSQL connectivity")
    listed = subcommands.add_parser("list-documents", help="List documents stored in PostgreSQL")
    listed.add_argument("--limit", type=int, default=100)
    listed.add_argument(
        "--status", choices=["pending", "ready", "requires_ocr", "failed", "deleted"]
    )
    return parser


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    try:
        exit_code = asyncio.run(_dispatch(args, get_settings()))
    except KeyboardInterrupt:
        exit_code = 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        exit_code = 1
    raise SystemExit(exit_code)


async def _dispatch(args: argparse.Namespace, settings: Settings) -> int:
    if args.command == "estimate-index":
        return await _estimate(settings, metadata_only=args.metadata_only, limit=args.limit)
    if args.command == "sync":
        return await _sync(
            settings,
            limit=args.limit,
            full=args.full,
            commit=args.commit,
            confirm=args.confirm,
            page_token=args.page_token,
            source_ids=args.source_ids,
        )
    if args.command == "verify-index":
        store = _pinecone(settings)
        await store.validate_dimension()
        print(f"Pinecone dimension matches: {settings.embedding_dimension}")
        return 0
    if args.command == "drive-token":
        print(await _drive(settings).get_start_page_token())
        return 0
    if args.command == "db-check":
        engine = create_engine(settings.sqlalchemy_url)
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            print("PostgreSQL connection: OK")
        finally:
            await engine.dispose()
        return 0
    if args.command == "list-documents":
        return await _list_documents(settings, limit=args.limit, status=args.status)
    return 2


async def _list_documents(settings: Settings, *, limit: int, status: str | None) -> int:
    if limit < 1:
        raise ValueError("--limit must be at least 1")
    engine = create_engine(settings.sqlalchemy_url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            statement = (
                select(
                    DriveFile.folder_path,
                    DriveFile.name,
                    Document.document_type,
                    Document.status,
                    func.count(DocumentChunk.id),
                )
                .join(Document, Document.drive_file_id == DriveFile.id)
                .outerjoin(
                    DocumentChunk,
                    (DocumentChunk.document_id == Document.id)
                    & DocumentChunk.active.is_(True),
                )
                .group_by(
                    DriveFile.folder_path,
                    DriveFile.name,
                    Document.document_type,
                    Document.status,
                )
                .order_by(DriveFile.folder_path, DriveFile.name)
                .limit(limit)
            )
            if status:
                statement = statement.where(Document.status == status)
            rows = (await session.execute(statement)).all()
        for folder, name, document_type, document_status, chunks in rows:
            path = name if folder in {"", "."} else f"{folder}/{name}"
            print(f"{document_status:12} chunks={chunks:<5} type={document_type:<15} {path}")
        print(f"Documents shown: {len(rows)}")
        return 0
    finally:
        await engine.dispose()


def _drive(settings: Settings) -> GoogleDriveDocumentSource:
    if settings.google_auth_mode == "oauth2":
        return GoogleDriveDocumentSource.from_oauth2(
            str(settings.google_oauth_client_file),
            str(settings.google_oauth_token_file),
            root_folder_id=settings.google_drive_root_folder_id,
        )
    return GoogleDriveDocumentSource.from_service_account(
        str(settings.google_service_account_file),
        root_folder_id=settings.google_drive_root_folder_id,
    )


async def _estimate(settings: Settings, *, metadata_only: bool, limit: int | None) -> int:
    drive = _drive(settings)
    documents = [document async for document in drive.list_documents(limit=limit)]
    layers: dict[str, bool] = {}
    if not metadata_only:
        for document in documents:
            if document.mime_type != "application/pdf":
                continue
            content = await drive.download(document)
            pages = PdfParser._extract_pages(content)
            layers[document.source_id] = (
                bool(pages)
                and sum(page.char_count for page in pages) >= settings.ocr_min_text_chars
            )
    report = CapacityEstimator(
        embedding_dimension=settings.embedding_dimension,
        warning_limit_mb=settings.pinecone_storage_warning_mb,
    ).estimate(documents, pdf_text_layer=layers)
    print(report.render())
    return 2 if report.status == "LIMIT_EXCEEDED" else 0


async def _sync(
    settings: Settings,
    *,
    limit: int,
    full: bool,
    commit: bool,
    confirm: bool,
    page_token: str | None = None,
    source_ids: list[str] | None = None,
) -> int:
    if source_ids and (full or page_token):
        raise ValueError("--source-id cannot be combined with --full or --page-token")
    if full and (not commit or not confirm):
        raise ValueError("Full sync requires both --commit and --confirm")
    if commit and not confirm:
        raise ValueError("External writes require --confirm")
    if full and settings.initial_sync_dry_run:
        raise ValueError("Set INITIAL_SYNC_DRY_RUN=false only after inspecting estimate and sample")
    drive = _drive(settings)
    ocr = TesseractOCRProvider(languages=settings.ocr_languages) if settings.ocr_enabled else None
    registry = ParserRegistry(
        [
            PdfParser(
                min_text_chars=settings.ocr_min_text_chars,
                ocr_enabled=settings.ocr_enabled,
                ocr_provider=ocr,
            ),
            DocxParser(),
            SpreadsheetParser(),
            TextParser(),
        ]
    )
    chunker = DocumentChunker(
        target_words=max(50, settings.chunk_target_tokens * 3 // 4),
        overlap_words=max(0, settings.chunk_overlap_tokens * 3 // 4),
        max_chunks=settings.max_chunks_per_document,
    )
    engine = None
    if commit:
        pinecone_store = _pinecone(settings)
        await pinecone_store.validate_dimension()
        vector_store: VectorStore = pinecone_store
        embeddings = _embeddings(settings)
        engine = create_engine(settings.sqlalchemy_url)
        factory = create_session_factory(engine)
        tenant_id, data_source_id = await _bootstrap(factory, settings)
        store: IngestionStore = SQLAlchemyIngestionStore(
            factory, data_source_id=data_source_id
        )
        audit = SQLAlchemyAuditSink(factory)
    else:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        vector_store = InMemoryVectorStore()
        embeddings = FakeEmbeddingProvider(settings.embedding_dimension)
        store = InMemoryIngestionStore()
        audit = None
    try:
        service = IngestionService(
            source=drive,
            parsers=registry,
            chunker=chunker,
            embeddings=embeddings,
            vector_store=vector_store,
            store=store,
            embedding_model=settings.embedding_model,
            max_file_size_bytes=settings.max_file_size_mb * 1024 * 1024,
            audit=audit,
        )
        if source_ids:
            requested_ids = list(dict.fromkeys(source_ids))
            requested = set(requested_ids)
            documents = {}
            async for candidate in drive.list_documents():
                if candidate.source_id in requested:
                    documents[candidate.source_id] = candidate
                if len(documents) == len(requested):
                    break
            missing = [item for item in requested_ids if item not in documents]
            if missing:
                raise ValueError(
                    "Google Drive files not found under configured root: " + ", ".join(missing)
                )
            failures = 0
            for requested_id in requested_ids:
                document = documents[requested_id]
                try:
                    outcome = await service.process_document(
                        document, tenant_id=tenant_id, dry_run=not commit
                    )
                except Exception as exc:
                    failures += 1
                    print(f"Source sync failed: {document.folder_path}/{document.name}: {exc}")
                    continue
                path = (
                    document.name
                    if document.folder_path in {"", "."}
                    else f"{document.folder_path}/{document.name}"
                )
                print(f"Source sync: status={outcome.value} {path}")
            if commit:
                await _save_manifest(factory, tenant_id, settings)
            return 1 if failures else 0
        if page_token:
            counters, next_token = await service.sync_changes(
                tenant_id=tenant_id, page_token=page_token, dry_run=not commit
            )
            print(f"Next Drive page token: {next_token}")
        else:
            counters = await service.sync(
                tenant_id=tenant_id,
                limit=None if full else limit,
                dry_run=not commit,
            )
        if commit:
            await _save_manifest(factory, tenant_id, settings)
        print(counters)
        return 1 if counters.failed else 0
    finally:
        if engine is not None:
            await engine.dispose()


def _embeddings(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "http":
        return HTTPEmbeddingProvider(
            settings.embedding_http_url,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            api_key=settings.embedding_http_api_key.get_secret_value(),
        )
    cache = EmbeddingCache(Path(settings.cache_dir) / "embeddings.sqlite3")
    return LocalQwenEmbeddingProvider(
        model_name=settings.embedding_model,
        dimension=settings.embedding_dimension,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        max_length=settings.embedding_max_length,
        cache=cache,
    )


def _pinecone(settings: Settings) -> PineconeVectorStore:
    return PineconeVectorStore(
        api_key=settings.pinecone_api_key.get_secret_value(),
        index_name=settings.pinecone_index,
        host=settings.pinecone_host,
        expected_dimension=settings.embedding_dimension,
        namespace_prefix=settings.pinecone_namespace_prefix,
    )


async def _bootstrap(
    factory: async_sessionmaker[AsyncSession], settings: Settings
) -> tuple[UUID, UUID]:
    async with factory() as session, session.begin():
        tenant = await session.scalar(select(Tenant).where(Tenant.name == "default"))
        if tenant is None:
            tenant = Tenant(name="default")
            session.add(tenant)
            await session.flush()
        source = await session.scalar(
            select(DataSource).where(
                DataSource.tenant_id == tenant.id,
                DataSource.name == "Google Drive",
            )
        )
        if source is None:
            source = DataSource(
                tenant_id=tenant.id,
                kind="google_drive",
                name="Google Drive",
                config={"root_folder_id": settings.google_drive_root_folder_id},
            )
            session.add(source)
            await session.flush()
        return tenant.id, source.id


async def _save_manifest(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID, settings: Settings
) -> None:
    async with factory() as session, session.begin():
        total_documents = await session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.tenant_id == tenant_id, Document.status == "ready")
        )
        total_chunks = await session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.active.is_(True),
            )
        )
        session.add(
            IndexManifestRecord(
                tenant_id=tenant_id,
                embedding_model=settings.embedding_model,
                embedding_dimension=settings.embedding_dimension,
                chunker_version=CHUNKER_VERSION,
                parser_versions={
                    "pdf": PdfParser.version,
                    "docx": DocxParser.version,
                    "spreadsheet": SpreadsheetParser.version,
                    "text": TextParser.version,
                },
                normalizer_version="german_normalizer:v1",
                total_documents=int(total_documents or 0),
                total_chunks=int(total_chunks or 0),
            )
        )
