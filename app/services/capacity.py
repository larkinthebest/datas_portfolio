from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.domain.models import SourceDocument


@dataclass(slots=True)
class CapacityReport:
    files: int = 0
    total_source_bytes: int = 0
    mime_types: Counter[str] = field(default_factory=Counter)
    folders: Counter[str] = field(default_factory=Counter)
    years: Counter[str] = field(default_factory=Counter)
    pdf_files: int = 0
    pdf_with_text_layer: int = 0
    pdf_requires_ocr: int = 0
    estimated_chunks: int = 0
    embedding_dimension: int = 1024
    estimated_vector_bytes: int = 0
    estimated_metadata_bytes: int = 0
    projected_storage_bytes: int = 0
    warning_limit_bytes: int = 0

    @property
    def status(self) -> str:
        if not self.warning_limit_bytes:
            return "SAFE"
        ratio = self.projected_storage_bytes / self.warning_limit_bytes
        if ratio >= 1:
            return "LIMIT_EXCEEDED"
        if ratio >= 0.8:
            return "WARNING"
        return "SAFE"

    def render(self) -> str:
        mib = 1024 * 1024
        lines = [
            f"Files: {self.files}",
            f"PDF: {self.pdf_files}",
            f"PDF with text layer: {self.pdf_with_text_layer}",
            f"Requires OCR: {self.pdf_requires_ocr}",
            f"Source size: {self.total_source_bytes / mib:.2f} MiB",
            f"Estimated chunks/vectors: {self.estimated_chunks}",
            f"Embedding dimension: {self.embedding_dimension}",
            f"Estimated vector storage: {self.estimated_vector_bytes / mib:.2f} MiB",
            f"Estimated metadata storage: {self.estimated_metadata_bytes / mib:.2f} MiB",
            f"Projected Pinecone storage: {self.projected_storage_bytes / mib:.2f} MiB",
            f"Status: {self.status}",
        ]
        lines.append(
            "MIME types: "
            + ", ".join(f"{key}={value}" for key, value in self.mime_types.most_common())
        )
        lines.append(
            "Folders: " + ", ".join(f"{key}={value}" for key, value in self.folders.most_common(20))
        )
        lines.append(
            "Years: " + ", ".join(f"{key}={value}" for key, value in sorted(self.years.items()))
        )
        return "\n".join(lines)


class CapacityEstimator:
    def __init__(
        self,
        *,
        embedding_dimension: int,
        warning_limit_mb: int,
        average_chunk_bytes: int = 2800,
        metadata_bytes_per_vector: int = 700,
    ) -> None:
        self.embedding_dimension = embedding_dimension
        self.warning_limit_bytes = warning_limit_mb * 1024 * 1024
        self.average_chunk_bytes = average_chunk_bytes
        self.metadata_bytes_per_vector = metadata_bytes_per_vector

    def estimate(
        self,
        documents: list[SourceDocument],
        *,
        pdf_text_layer: dict[str, bool] | None = None,
    ) -> CapacityReport:
        layer = pdf_text_layer or {}
        report = CapacityReport(
            embedding_dimension=self.embedding_dimension,
            warning_limit_bytes=self.warning_limit_bytes,
        )
        for document in documents:
            report.files += 1
            report.total_source_bytes += document.size or 0
            report.mime_types[document.source_mime_type or document.mime_type] += 1
            report.folders[document.folder_path or "/"] += 1
            for part in document.folder_path.split("/"):
                if part.isdigit() and len(part) == 4:
                    report.years[part] += 1
            if document.mime_type == "application/pdf":
                report.pdf_files += 1
                if document.source_id in layer:
                    if layer[document.source_id]:
                        report.pdf_with_text_layer += 1
                    else:
                        report.pdf_requires_ocr += 1
        source_bytes = report.total_source_bytes or report.files * self.average_chunk_bytes
        report.estimated_chunks = max(
            report.files, (source_bytes + self.average_chunk_bytes - 1) // self.average_chunk_bytes
        )
        report.estimated_vector_bytes = report.estimated_chunks * self.embedding_dimension * 4
        report.estimated_metadata_bytes = report.estimated_chunks * self.metadata_bytes_per_vector
        report.projected_storage_bytes = (
            report.estimated_vector_bytes + report.estimated_metadata_bytes
        )
        return report
