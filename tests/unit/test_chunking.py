from uuid import UUID

from app.domain.models import ParsedDocument, ParsedPage
from app.rag.chunking import DocumentChunker

TENANT = UUID("00000000-0000-0000-0000-000000000001")
DOCUMENT = UUID("00000000-0000-0000-0000-000000000002")


def test_chunk_ids_are_stable_and_page_anchored() -> None:
    parsed = ParsedDocument(
        pages=[
            ParsedPage(
                page_number=2,
                text="Die Heizkosten betragen 940,00 €.",
                char_count=35,
                has_text_layer=True,
            )
        ],
        original_text="Die Heizkosten betragen 940,00 €.",
        normalized_text="Die Heizkosten betragen 940,00 €.",
        parser_version="test:v1",
    )
    chunker = DocumentChunker(target_words=20, overlap_words=2)
    first = chunker.chunk(parsed, tenant_id=TENANT, document_id=DOCUMENT, document_version="v1")
    second = chunker.chunk(parsed, tenant_id=TENANT, document_id=DOCUMENT, document_version="v1")
    assert first[0].chunk_id == second[0].chunk_id
    assert first[0].page == 2
    assert first[0].content_hash == second[0].content_hash


def test_chunker_rejects_invalid_overlap() -> None:
    try:
        DocumentChunker(target_words=10, overlap_words=10)
    except ValueError as error:
        assert "overlap" in str(error)
    else:
        raise AssertionError("Expected invalid overlap to fail")
