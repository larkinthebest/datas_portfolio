from io import BytesIO

import fitz
import pytest
from openpyxl import Workbook

from app.domain.models import ProcessingStatus
from app.parsers.pdf import PdfParser
from app.parsers.spreadsheet import SpreadsheetParser


def _pdf_bytes(text: str | None) -> bytes:
    document = fitz.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


@pytest.mark.asyncio
async def test_pdf_text_layer_detection() -> None:
    parsed = await PdfParser(min_text_chars=10).parse(
        _pdf_bytes("Kontoauszug mit ausreichendem Text"), file_name="statement.pdf"
    )
    assert parsed.status == ProcessingStatus.READY
    assert parsed.pages[0].has_text_layer is True


@pytest.mark.asyncio
async def test_pdf_requires_ocr_instead_of_empty_index() -> None:
    parsed = await PdfParser(min_text_chars=10, ocr_enabled=False).parse(
        _pdf_bytes(None), file_name="scan.pdf"
    )
    assert parsed.status == ProcessingStatus.REQUIRES_OCR
    assert parsed.normalized_text == ""


@pytest.mark.asyncio
async def test_spreadsheet_preserves_rows_and_headers() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Kosten 2025"
    sheet.append(["Kostenart", "Betrag"])
    sheet.append(["Grundsteuer", "168,88 EUR"])
    output = BytesIO()
    workbook.save(output)
    parsed = await SpreadsheetParser().parse(output.getvalue(), file_name="kosten.xlsx")
    assert parsed.rows[0].sheet_name == "Kosten 2025"
    assert parsed.rows[0].column_headers == ["Kostenart", "Betrag"]
    assert "Grundsteuer" in parsed.normalized_text
