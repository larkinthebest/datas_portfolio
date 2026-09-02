from __future__ import annotations

import asyncio

import fitz

from app.domain.german import normalize_german_text
from app.domain.models import ParsedDocument, ParsedPage, ProcessingStatus
from app.parsers.base import OCRProvider


class PdfParser:
    version = "pdf_parser:v1"
    supported_mime_types = frozenset({"application/pdf"})

    def __init__(
        self,
        *,
        min_text_chars: int = 80,
        ocr_enabled: bool = False,
        ocr_provider: OCRProvider | None = None,
    ) -> None:
        self.min_text_chars = min_text_chars
        self.ocr_enabled = ocr_enabled
        self.ocr_provider = ocr_provider

    async def parse(self, content: bytes, *, file_name: str) -> ParsedDocument:
        pages = await asyncio.to_thread(self._extract_pages, content)
        total_chars = sum(page.char_count for page in pages)
        sparse_pages = sum(page.char_count < self.min_text_chars for page in pages)
        needs_ocr = total_chars < self.min_text_chars or (
            bool(pages) and sparse_pages > len(pages) / 2
        )
        warnings: list[str] = []
        if needs_ocr:
            if not self.ocr_enabled or self.ocr_provider is None:
                return ParsedDocument(
                    pages=pages,
                    original_text="\n\n".join(page.text for page in pages),
                    normalized_text="",
                    status=ProcessingStatus.REQUIRES_OCR,
                    parser_version=self.version,
                    warnings=["PDF has insufficient text layer; OCR is required"],
                )
            ocr_texts = await self.ocr_provider.process_pdf(content)
            pages = [
                ParsedPage(
                    page_number=index,
                    text=text,
                    char_count=len(text.strip()),
                    has_text_layer=False,
                )
                for index, text in enumerate(ocr_texts, start=1)
            ]
            warnings.append("Text was produced by OCR and should be reviewed")
        original = "\n\n".join(page.text for page in pages)
        normalized = normalize_german_text(original)
        if not normalized:
            return ParsedDocument(
                pages=pages,
                original_text=original,
                normalized_text="",
                status=ProcessingStatus.FAILED,
                parser_version=self.version,
                warnings=[*warnings, "Parser produced empty text"],
            )
        return ParsedDocument(
            pages=pages,
            original_text=original,
            normalized_text=normalized,
            parser_version=self.version,
            warnings=warnings,
        )

    @staticmethod
    def _extract_pages(content: bytes) -> list[ParsedPage]:
        document = fitz.open(stream=content, filetype="pdf")
        try:
            result: list[ParsedPage] = []
            for index, page in enumerate(document, start=1):
                text = page.get_text("text")
                stripped_length = len(text.strip())
                result.append(
                    ParsedPage(
                        page_number=index,
                        text=text,
                        char_count=stripped_length,
                        has_text_layer=stripped_length > 0,
                    )
                )
            return result
        finally:
            document.close()
