from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.core.telemetry import AGENT_TOOL_CALLS

ToolFunction = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class TrustedTool:
    name: str
    description: str
    permission: str
    function: ToolFunction


class BoundedToolExecutor:
    """Runs allow-listed tools with hard per-request limits and no dynamic code access."""

    def __init__(
        self,
        tools: list[TrustedTool],
        *,
        max_tool_calls: int = 8,
        timeout_seconds: int = 45,
        audit: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self.tools = {tool.name: tool for tool in tools}
        self.max_tool_calls = max_tool_calls
        self.timeout_seconds = timeout_seconds
        self.audit = audit

    async def execute(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        *,
        allowed_permissions: set[str],
    ) -> list[dict[str, Any]]:
        if len(calls) > self.max_tool_calls:
            raise ValueError(f"Agent exceeded the {self.max_tool_calls} tool-call limit")
        results: list[dict[str, Any]] = []
        async with asyncio.timeout(self.timeout_seconds):
            for name, arguments in calls:
                tool = self.tools.get(name)
                if tool is None:
                    raise ValueError(f"Tool is not allow-listed: {name}")
                if tool.permission not in allowed_permissions and "*" not in allowed_permissions:
                    raise PermissionError(f"Permission denied for tool: {name}")
                if self.audit:
                    await self.audit("agent_tool_call", {"tool": name})
                AGENT_TOOL_CALLS.labels(tool=name).inc()
                results.append(await tool.function(arguments))
        return results


def detect_intent(query: str) -> str:
    normalized = query.casefold()
    if any(value in normalized for value in ("end-to-end", "операц", "транзакц")):
        return "transaction_search"
    if any(value in normalized for value in ("сколько", "итого", "сумм")):
        return "financial_summary"
    if any(value in normalized for value in ("свер", "reconciliation", "несопостав")):
        return "reconciliation"
    if any(value in normalized for value in ("закон", "правил", "налогов")):
        return "legal_question"
    if any(value in normalized for value in ("статус", "health")):
        return "system_status"
    return "document_question"
