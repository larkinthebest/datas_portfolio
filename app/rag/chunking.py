from __future__ import annotations

import hashlib
from collections.abc import Iterable
from uuid import NAMESPACE_URL, UUID, uuid5

from app.domain.models import BankTransaction, DocumentChunk, ParsedDocument
from app.parsers.spreadsheet import SpreadsheetParser

CHUNKER_VERSION = "document_aware_chunker:v1"


def stable_chunk_id(
    tenant_id: UUID,
    document_id: UUID,
    document_version: str,
    chunk_index: int,
    content_hash: str,
) -> str:
    source = f"{tenant_id}:{document_id}:{document_version}:{chunk_index}:{content_hash}"
    return str(uuid5(NAMESPACE_URL, source))


class DocumentChunker:
    def __init__(self, *, target_words: int = 500, overlap_words: int = 50, max_chunks: int = 2000):
        if overlap_words >= target_words:
            raise ValueError("overlap_words must be smaller than target_words")
        self.target_words = target_words
        self.overlap_words = overlap_words
        self.max_chunks = max_chunks

    def chunk(
        self,
        document: ParsedDocument,
        *,
        tenant_id: UUID,
        document_id: UUID,
        document_version: str,
    ) -> list[DocumentChunk]:
        anchored_texts: list[tuple[str, int | None, str | None, int | None]] = []
        if document.rows:
            anchored_texts.extend(
                (SpreadsheetParser.render_row(row), None, row.sheet_name, row.row_number)
                for row in document.rows
            )
        else:
            anchored_texts.extend(
                (page.text, page.page_number, None, None)
                for page in document.pages
                if page.text.strip()
            )
        raw_chunks: list[tuple[str, int | None, str | None, int | None]] = []
        for text, page, sheet, row in anchored_texts:
            raw_chunks.extend((part, page, sheet, row) for part in self._split(text))
        if len(raw_chunks) > self.max_chunks:
            raise ValueError(f"Document exceeds maximum of {self.max_chunks} chunks")
        return [
            self._build_chunk(
                text,
                index=index,
                tenant_id=tenant_id,
                document_id=document_id,
                document_version=document_version,
                parser_version=document.parser_version,
                page=page,
                sheet=sheet,
                row=row,
            )
            for index, (text, page, sheet, row) in enumerate(raw_chunks)
        ]

    def chunk_transactions(
        self,
        transactions: Iterable[BankTransaction],
        *,
        statement_header: str,
        tenant_id: UUID,
        document_id: UUID,
        document_version: str,
        parser_version: str,
    ) -> list[DocumentChunk]:
        result: list[DocumentChunk] = []
        for index, transaction in enumerate(transactions):
            text = (
                f"{statement_header}\n"
                f"Buchungsdatum: {transaction.booking_date.isoformat()}\n"
                f"Betrag: {transaction.amount} {transaction.currency}\n"
                f"Gegenpartei: {transaction.counterparty or ''}\n"
                f"Referenz: {transaction.end_to_end_reference or transaction.reference or ''}\n"
                f"{transaction.raw_text}"
            )
            result.append(
                self._build_chunk(
                    text,
                    index=index,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    document_version=document_version,
                    parser_version=parser_version,
                    page=transaction.statement_page,
                    sheet=None,
                    row=None,
                )
            )
        return result

    def _split(self, text: str) -> list[str]:
        words = text.split()
        if not words:
            return []
        step = self.target_words - self.overlap_words
        return [
            " ".join(words[start : start + self.target_words])
            for start in range(0, len(words), step)
        ]

    @staticmethod
    def _build_chunk(
        text: str,
        *,
        index: int,
        tenant_id: UUID,
        document_id: UUID,
        document_version: str,
        parser_version: str,
        page: int | None,
        sheet: str | None,
        row: int | None,
    ) -> DocumentChunk:
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return DocumentChunk(
            chunk_id=stable_chunk_id(tenant_id, document_id, document_version, index, content_hash),
            document_id=document_id,
            document_version=document_version,
            chunk_index=index,
            text=text,
            content_hash=content_hash,
            page=page,
            sheet=sheet,
            row_from=row,
            row_to=row,
            parser_version=parser_version,
            chunker_version=CHUNKER_VERSION,
        )
