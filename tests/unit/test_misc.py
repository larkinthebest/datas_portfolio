from datetime import date
from uuid import UUID

from app.domain.legal import LegalRuleVersion, select_legal_rule
from app.domain.models import DocumentChunk, SourceDocument
from app.integrations.pinecone import build_vector_metadata
from app.services.capacity import CapacityEstimator
from app.services.hashing import duplicate_kind


def test_duplicate_detection() -> None:
    assert (
        duplicate_kind(
            binary_hash="a", text_hash="b", existing_binary_hash="a", existing_text_hash="x"
        )
        == "exact_duplicate"
    )
    assert (
        duplicate_kind(
            binary_hash="a", text_hash="b", existing_binary_hash="x", existing_text_hash="b"
        )
        == "content_duplicate"
    )


def test_only_approved_effective_legal_rule_is_selected() -> None:
    rules = [
        LegalRuleVersion(
            rule_code="AFA", valid_from=date(2024, 1, 1), version=1, review_status="approved"
        ),
        LegalRuleVersion(
            rule_code="AFA", valid_from=date(2025, 1, 1), version=2, review_status="draft"
        ),
    ]
    assert select_legal_rule(rules, rule_code="AFA", effective_on=date(2025, 6, 1)) == rules[0]


def test_pinecone_metadata_excludes_full_text() -> None:
    chunk = DocumentChunk(
        chunk_id="c1",
        document_id=UUID("00000000-0000-0000-0000-000000000001"),
        document_version="v1",
        chunk_index=0,
        text="sensitive full document text",
        content_hash="hash",
        parser_version="p:v1",
        chunker_version="c:v1",
    )
    metadata = build_vector_metadata(
        chunk,
        tenant_id="tenant",
        file_name="a.pdf",
        drive_file_id="drive",
        folder_path="Bank/2025",
        document_type="bank_statement",
    )
    assert "text" not in metadata
    assert "sensitive" not in str(metadata)


def test_capacity_estimator_warns_at_limit() -> None:
    documents = [
        SourceDocument(
            source_id="1",
            name="a.pdf",
            mime_type="application/pdf",
            folder_path="Bank/2025",
            size=10_000_000,
        )
    ]
    report = CapacityEstimator(embedding_dimension=1024, warning_limit_mb=1).estimate(
        documents, pdf_text_layer={"1": False}
    )
    assert report.pdf_requires_ocr == 1
    assert report.status == "LIMIT_EXCEEDED"
