from __future__ import annotations

import asyncio
from typing import Any

from app.cli import _sync
from app.core.config import get_settings
from app.tasks.celery_app import celery_app


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=5
)
def run_sync(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Run Drive synchronization in a worker, never in an HTTP/Telegram handler."""
    if not payload.get("dry_run", True) and not payload.get("confirmed", False):
        return {
            "status": "needs_confirmation",
            "message": "A non-dry-run sync requires explicit confirmed=true from an admin workflow.",
        }
    dry_run = bool(payload.get("dry_run", True))
    exit_code = asyncio.run(
        _sync(
            get_settings(),
            limit=int(payload.get("limit") or 20),
            full=bool(payload.get("full", False)),
            commit=not dry_run,
            confirm=bool(payload.get("confirmed", False)),
            page_token=str(payload["page_token"]) if payload.get("page_token") else None,
        )
    )
    return {"status": "completed" if exit_code == 0 else "completed_with_warnings"}
