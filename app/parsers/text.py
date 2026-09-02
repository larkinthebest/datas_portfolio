from __future__ import annotations

from app.domain.german import normalize_german_text
from app.domain.models import ParsedDocument, ParsedPage, ProcessingStatus


class TextParser:
    version = "text_parser:v1"
    supported_mime_types = frozenset({"text/plain", "text/markdown", "text/csv", "application/csv"})

    async def parse(self, content: bytes, *, file_name: str) -> ParsedDocument:
        text = content.decode("utf-8-sig", errors="replace")
        normalized = normalize_german_text(text)
        return ParsedDocument(
            pages=[
                ParsedPage(
                    page_number=1,
                    text=text,
                    char_count=len(text.strip()),
                    has_text_layer=True,
                )
            ],
            original_text=text,
            normalized_text=normalized,
            status=ProcessingStatus.READY if normalized else ProcessingStatus.FAILED,
            parser_version=self.version,
        )
