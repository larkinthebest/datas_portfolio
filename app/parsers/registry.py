from __future__ import annotations

from app.core.exceptions import UnsupportedDocumentError
from app.parsers.base import DocumentParser


class ParserRegistry:
    def __init__(self, parsers: list[DocumentParser]) -> None:
        self._by_mime = {
            mime_type: parser for parser in parsers for mime_type in parser.supported_mime_types
        }

    def get(self, mime_type: str) -> DocumentParser:
        try:
            return self._by_mime[mime_type]
        except KeyError as exc:
            raise UnsupportedDocumentError(f"Unsupported MIME type: {mime_type}") from exc

    @property
    def supported_mime_types(self) -> frozenset[str]:
        return frozenset(self._by_mime)
