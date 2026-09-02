from __future__ import annotations

from typing import Protocol

from app.domain.models import ParsedDocument


class DocumentParser(Protocol):
    version: str
    supported_mime_types: frozenset[str]

    async def parse(self, content: bytes, *, file_name: str) -> ParsedDocument: ...


class OCRProvider(Protocol):
    async def process_pdf(self, content: bytes) -> list[str]: ...
