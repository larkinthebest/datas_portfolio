from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    BankAccount,
    BankTransaction,
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentVersion,
    DriveFile,
)
from app.domain.german import parse_account_folder
from app.domain.models import BankTransaction as DomainBankTransaction
from app.domain.models import DocumentChunk as DomainChunk
from app.domain.models import ParsedDocument, SourceDocument
from app.services.ingestion import StagedVersion


class SQLAlchemyIngestionStore:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        data_source_id: UUID,
    ) -> None:
        self.factory = factory
        self.data_source_id = data_source_id

    async def find_duplicate(
        self, *, tenant_id: UUID, source_id: str, binary_hash: str, text_hash: str
    ) -> tuple[UUID, str] | None:
        async with self.factory() as session:
            statement = (
                select(DocumentVersion, DriveFile)
                .join(Document, Document.id == DocumentVersion.document_id)
                .join(DriveFile, DriveFile.id == Document.drive_file_id)
                .where(
                    DocumentVersion.tenant_id == tenant_id,
                    DriveFile.drive_file_id != source_id,
                    DocumentVersion.status == "ready",
                )
            )
            for version, _ in (await session.execute(statement)).all():
                if version.sha256 == binary_hash:
                    return version.document_id, "exact_duplicate"
                if version.text_hash == text_hash:
                    return version.document_id, "content_duplicate"
        return None

    async def stage(
        self,
        *,
        tenant_id: UUID,
        source: SourceDocument,
        document_id: UUID,
        document_type: str,
        parsed: ParsedDocument,
        chunks: list[DomainChunk],
        transactions: list[DomainBankTransaction],
        binary_hash: str,
        text_hash: str,
        embedding_model: str,
        embedding_dimension: int,
        duplicate: tuple[UUID, str] | None = None,
    ) -> StagedVersion:
        version_uuid = uuid5(NAMESPACE_URL, f"{document_id}:{binary_hash}")
        async with self.factory() as session, session.begin():
            drive_file = await session.scalar(
                select(DriveFile).where(
                    DriveFile.tenant_id == tenant_id,
                    DriveFile.drive_file_id == source.source_id,
                )
            )
            if drive_file is None:
                drive_file = DriveFile(
                    tenant_id=tenant_id,
                    source_id=self.data_source_id,
                    drive_file_id=source.source_id,
                    name=source.name,
                    mime_type=source.mime_type,
                    folder_path=source.folder_path,
                )
                session.add(drive_file)
                await session.flush()
            drive_file.name = source.name
            drive_file.mime_type = source.mime_type
            drive_file.folder_path = source.folder_path
            drive_file.web_url = source.web_url
            drive_file.drive_modified_time = source.modified_time
            drive_file.size = source.size
            drive_file.checksum = source.checksum
            drive_file.deleted = False
            document = await session.get(Document, document_id)
            if document is None:
                document = Document(
                    id=document_id,
                    tenant_id=tenant_id,
                    drive_file_id=drive_file.id,
                    status="pending",
                    document_type=document_type,
                )
                session.add(document)
                await session.flush()
            previous = str(document.active_version_id) if document.active_version_id else None
            document.document_type = document_type
            if duplicate:
                document.duplicate_of_id, document.duplicate_kind = duplicate
            if document.active_version_id is not None:
                active_version = await session.get(DocumentVersion, document.active_version_id)
                if (
                    active_version is not None
                    and active_version.status == "ready"
                    and active_version.text_hash == text_hash
                    and active_version.parser_version == parsed.parser_version
                ):
                    return StagedVersion(
                        document_id,
                        str(active_version.id),
                        previous,
                        unchanged=True,
                    )
            existing_version = await session.get(DocumentVersion, version_uuid)
            if existing_version is not None:
                unchanged = (
                    existing_version.status == "ready"
                    and document.active_version_id == version_uuid
                )
                return StagedVersion(
                    document_id,
                    str(version_uuid),
                    previous,
                    unchanged=unchanged,
                )
            version = DocumentVersion(
                id=version_uuid,
                tenant_id=tenant_id,
                document_id=document_id,
                drive_revision=source.checksum or binary_hash,
                sha256=binary_hash,
                text_hash=text_hash,
                parser_version=parsed.parser_version,
                status="pending",
                original_text=parsed.original_text,
                normalized_text=parsed.normalized_text,
            )
            session.add(version)
            # Persist the parent row before adding pages, chunks, and transactions.
            # These models only carry FK identifiers (no ORM relationships), so an
            # explicit flush keeps PostgreSQL insert ordering deterministic.
            await session.flush()
            for page in parsed.pages:
                session.add(
                    DocumentPage(
                        tenant_id=tenant_id,
                        document_version_id=version_uuid,
                        page_number=page.page_number,
                        original_text=page.text,
                        normalized_text=page.text,
                        has_text_layer=page.has_text_layer,
                    )
                )
            for chunk in chunks:
                session.add(
                    DocumentChunk(
                        tenant_id=tenant_id,
                        chunk_id=chunk.chunk_id,
                        document_id=document_id,
                        document_version_id=version_uuid,
                        chunk_index=chunk.chunk_index,
                        original_text=chunk.text,
                        normalized_text=chunk.text,
                        content_hash=chunk.content_hash,
                        page=chunk.page,
                        sheet=chunk.sheet,
                        row_from=chunk.row_from,
                        row_to=chunk.row_to,
                        section=chunk.section,
                        parser_version=chunk.parser_version,
                        chunker_version=chunk.chunker_version,
                        embedding_model=embedding_model,
                        embedding_dimension=embedding_dimension,
                        active=False,
                        metadata_json=chunk.metadata,
                    )
                )
            if transactions:
                folder = parse_account_folder(source.folder_path)
                account = await session.scalar(
                    select(BankAccount).where(
                        BankAccount.tenant_id == tenant_id,
                        BankAccount.account_code == folder.account_code,
                        BankAccount.label == (folder.account_label or "Unknown account"),
                    )
                )
                if account is None:
                    account = BankAccount(
                        tenant_id=tenant_id,
                        label=folder.account_label or "Unknown account",
                        account_code=folder.account_code,
                        account_role=folder.account_role,
                        currency=folder.expected_currency or transactions[0].currency,
                        folder_path=source.folder_path,
                    )
                    session.add(account)
                    await session.flush()
                for transaction in transactions:
                    session.add(
                        BankTransaction(
                            tenant_id=tenant_id,
                            account_id=account.id,
                            statement_document_id=document_id,
                            document_version_id=version_uuid,
                            active=False,
                            statement_page=transaction.statement_page,
                            booking_date=transaction.booking_date,
                            value_date=transaction.value_date,
                            amount=transaction.amount,
                            currency=transaction.currency,
                            direction=transaction.direction.value,
                            counterparty=transaction.counterparty,
                            iban=transaction.iban,
                            bic=transaction.bic,
                            reference=transaction.reference,
                            booking_text=transaction.booking_text,
                            end_to_end_reference=transaction.end_to_end_reference,
                            mandate_reference=transaction.mandate_reference,
                            creditor_id=transaction.creditor_id,
                            raw_text=transaction.raw_text,
                            extraction_confidence=transaction.extraction_confidence,
                        )
                    )
        return StagedVersion(document_id, str(version_uuid), previous)

    async def activate(self, staged: StagedVersion) -> None:
        version_id = UUID(staged.version_id)
        async with self.factory() as session, session.begin():
            if staged.previous_version_id:
                await session.execute(
                    update(DocumentChunk)
                    .where(DocumentChunk.document_version_id == UUID(staged.previous_version_id))
                    .values(active=False)
                )
                await session.execute(
                    update(BankTransaction)
                    .where(BankTransaction.document_version_id == UUID(staged.previous_version_id))
                    .values(active=False)
                )
            await session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.document_version_id == version_id)
                .values(active=True)
            )
            await session.execute(
                update(BankTransaction)
                .where(BankTransaction.document_version_id == version_id)
                .values(active=True)
            )
            await session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == version_id)
                .values(status="ready", ready_at=datetime.now(UTC))
            )
            await session.execute(
                update(Document)
                .where(Document.id == staged.document_id)
                .values(status="ready", active_version_id=version_id)
            )

    async def fail(self, staged: StagedVersion, *, status: str, error: str) -> None:
        async with self.factory() as session, session.begin():
            await session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == UUID(staged.version_id))
                .values(status=status)
            )
            if staged.previous_version_id is None:
                await session.execute(
                    update(Document).where(Document.id == staged.document_id).values(status=status)
                )

    async def mark_deleted(self, *, tenant_id: UUID, source_id: str) -> str | None:
        async with self.factory() as session, session.begin():
            drive_file = await session.scalar(
                select(DriveFile).where(
                    DriveFile.tenant_id == tenant_id,
                    DriveFile.drive_file_id == source_id,
                )
            )
            if drive_file is None:
                return None
            document = await session.scalar(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.drive_file_id == drive_file.id,
                )
            )
            drive_file.deleted = True
            if document is None:
                return None
            document.status = "deleted"
            version_id = document.active_version_id
            if version_id is not None:
                await session.execute(
                    update(DocumentChunk)
                    .where(DocumentChunk.document_version_id == version_id)
                    .values(active=False)
                )
                await session.execute(
                    update(BankTransaction)
                    .where(BankTransaction.document_version_id == version_id)
                    .values(active=False)
                )
            return str(version_id) if version_id else None
