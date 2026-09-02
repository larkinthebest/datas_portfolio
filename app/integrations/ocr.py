from __future__ import annotations

import asyncio
from io import BytesIO

import fitz


class TesseractOCRProvider:
    def __init__(self, *, languages: str = "deu+eng", dpi: int = 300) -> None:
        self.languages = languages
        self.dpi = dpi

    async def process_pdf(self, content: bytes) -> list[str]:
        return await asyncio.to_thread(self._process, content)

    def _process(self, content: bytes) -> list[str]:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Install OCR dependencies with pip install -e '.[ocr]'") from exc
        document = fitz.open(stream=content, filetype="pdf")
        try:
            texts: list[str] = []
            for page in document:
                pixmap = page.get_pixmap(dpi=self.dpi, alpha=False)
                image = Image.open(BytesIO(pixmap.tobytes("png")))
                texts.append(pytesseract.image_to_string(image, lang=self.languages))
            return texts
        finally:
            document.close()
