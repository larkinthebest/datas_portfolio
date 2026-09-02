from __future__ import annotations

from typing import cast
from uuid import UUID

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_api_key
from app.api.schemas import AskRequest, SearchRequest, SyncRequest
from app.db.models import AuditEvent, BankTransaction, Document
from app.db.repositories import ChunkRepository
from app.domain.models import RagAnswer
from app.integrations.gemini import GeminiProvider
from app.rag.retrieval import HybridRetriever, SemanticRetriever
from app.rag.service import RagService
from app.tasks.jobs import run_sync

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED, summary="Queue Drive synchronization")
async def queue_sync(payload: SyncRequest) -> dict[str, str]:
    task = run_sync.delay(payload.model_dump(mode="json"))
    return {"job_id": task.id, "status": "queued"}


@router.get("/sync/{job_id}", summary="Get synchronization status")
async def sync_status(job_id: str) -> dict[str, object]:
    task = AsyncResult(job_id)
    return {
        "id": job_id,
        "status": task.state,
        "result": task.result if task.ready() else None,
    }


@router.get("/documents", summary="List tenant documents")
async def documents(
    tenant_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    rows = (
        await session.scalars(
            select(Document)
            .where(Document.tenant_id == tenant_id)
            .order_by(Document.updated_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {"id": str(row.id), "status": row.status, "document_type": row.document_type}
        for row in rows
    ]


@router.get("/documents/{document_id}", summary="Get document metadata")
async def document_detail(
    document_id: UUID,
    tenant_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    row = await session.scalar(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": str(row.id),
        "status": row.status,
        "document_type": row.document_type,
        "active_version_id": str(row.active_version_id) if row.active_version_id else None,
    }


@router.post("/search", summary="Run hybrid evidence search")
async def search(
    payload: SearchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    semantic = cast(
        SemanticRetriever | None,
        getattr(request.app.state, "semantic_retriever", None),
    )
    if semantic is None:
        raise HTTPException(status_code=503, detail="Retrieval service is not configured")
    chunks = ChunkRepository(session)
    retriever = HybridRetriever(
        semantic,
        chunks,
        chunks,
        semantic_k=request.app.state.settings.top_k_semantic,
        lexical_k=request.app.state.settings.top_k_lexical,
        final_k=request.app.state.settings.top_k_rerank,
    )
    normalized, hits = await retriever.search(payload.query, tenant_id=str(payload.tenant_id))
    return {
        "query": normalized.normalized_query,
        "expanded_terms": normalized.expanded_terms,
        "hits": hits,
    }


@router.post("/ask", response_model=RagAnswer, summary="Ask a grounded question")
async def ask(
    payload: AskRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RagAnswer:
    semantic = cast(
        SemanticRetriever | None,
        getattr(request.app.state, "semantic_retriever", None),
    )
    generator = cast(GeminiProvider | None, getattr(request.app.state, "gemini", None))
    if semantic is None or generator is None:
        raise HTTPException(status_code=503, detail="RAG service is not configured")
    chunks = ChunkRepository(session)
    service = RagService(
        retriever=HybridRetriever(
            semantic,
            chunks,
            chunks,
            semantic_k=request.app.state.settings.top_k_semantic,
            lexical_k=request.app.state.settings.top_k_lexical,
            final_k=request.app.state.settings.top_k_rerank,
        ),
        chunks=chunks,
        generator=generator,
    )
    return await service.ask(payload.query, tenant_id=payload.tenant_id)


@router.get("/transactions", summary="List bank transactions")
async def transactions(
    tenant_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    rows = (
        await session.scalars(
            select(BankTransaction)
            .where(
                BankTransaction.tenant_id == tenant_id,
                BankTransaction.active.is_(True),
            )
            .order_by(BankTransaction.booking_date.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "booking_date": row.booking_date,
            "amount": str(row.amount),
            "currency": row.currency,
            "counterparty": row.counterparty,
        }
        for row in rows
    ]


@router.get("/reconciliation/{status_name}", summary="List reconciliation items by status")
async def reconciliation(status_name: str) -> dict[str, object]:
    if status_name not in {"unmatched", "conflicts"}:
        raise HTTPException(status_code=404, detail="Unknown reconciliation view")
    return {"status": status_name, "items": []}


@router.get("/audit", summary="Read redacted audit events")
async def audit(
    tenant_id: UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    rows = (
        await session.scalars(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.timestamp.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "timestamp": row.timestamp,
            "event_type": row.event_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "metadata": row.metadata_json,
        }
        for row in rows
    ]
