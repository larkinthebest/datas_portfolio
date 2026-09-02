from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Dependency readiness probe")
async def ready(request: Request, response: Response) -> dict[str, object]:
    checks: dict[str, str] = {}
    try:
        async with request.app.state.session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["postgresql"] = "ok"
    except Exception as exc:
        checks["postgresql"] = f"error: {type(exc).__name__}"
    settings = request.app.state.settings
    checks["redis"] = "configured" if settings.redis_url else "missing"
    checks["google_drive"] = "configured" if settings.google_drive_root_folder_id else "missing"
    checks["pinecone"] = "configured" if settings.pinecone_index else "missing"
    checks["embedding_provider"] = settings.embedding_provider
    checks["gemini"] = (
        "disabled"
        if not settings.ai_external_processing_enabled
        else "configured"
        if settings.gemini_api_key.get_secret_value()
        else "missing"
    )
    healthy = checks["postgresql"] == "ok" and all(
        checks[name] not in {"missing"} for name in ("google_drive", "pinecone", "gemini")
    )
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if healthy else "not_ready", "checks": checks}


@router.get("/metrics", summary="Prometheus metrics", response_class=Response)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
