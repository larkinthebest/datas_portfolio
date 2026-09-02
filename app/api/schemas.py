from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SyncRequest(BaseModel):
    tenant_id: UUID
    full: bool = False
    dry_run: bool = True
    confirmed: bool = False
    page_token: str | None = None
    limit: int | None = Field(default=20, ge=1, le=10000)


class SearchRequest(BaseModel):
    tenant_id: UUID
    query: str = Field(min_length=2, max_length=2000)
    filters: dict[str, Any] = Field(default_factory=dict)


class AskRequest(BaseModel):
    tenant_id: UUID
    query: str = Field(min_length=2, max_length=2000)
