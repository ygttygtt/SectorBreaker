"""Tool registry and runtime context for the V2 Agent Kernel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from backend.app.agent_kernel.models import KernelObservation, ToolCall, ToolSpec
from backend.app.agent_state.models import SectorBreakerState
from backend.app.providers.interfaces import LLMProvider, SearchProvider
from backend.app.schemas import Artifact, ResearchProject, RunEvent
from backend.app.storage.sqlite import SQLiteRepository


ToolHandler = Callable[[ToolCall, "KernelRuntimeContext"], Awaitable[KernelObservation]]
EmitFn = Callable[[RunEvent], Awaitable[None]]


@dataclass
class KernelRuntimeContext:
    project: ResearchProject
    repository: SQLiteRepository
    state: SectorBreakerState
    search_provider: SearchProvider | None
    llm_provider: LLMProvider | None
    emit_event: EmitFn
    artifacts: list[Artifact] = field(default_factory=list)
    search_call_count: int = 0
    writer_call_count: int = 0
    # Optional callback: called after each successful artifact write for checkpointing
    on_artifact_written: Callable[[str, int], Awaitable[None]] | None = None


class ToolRegistry:
    """Typed dispatch table for approved Agent tools."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    async def dispatch(self, tool_call: ToolCall, context: KernelRuntimeContext) -> KernelObservation:
        handler = self._handlers.get(tool_call.tool_name)
        if handler is None:
            return KernelObservation(
                tool_name=tool_call.tool_name,
                success=False,
                summary=f"未知工具：{tool_call.tool_name}",
                error=f"unknown tool: {tool_call.tool_name}",
                data={"available_tools": list(self._specs)},
            )
        try:
            return await handler(tool_call, context)
        except Exception as exc:
            return KernelObservation(
                tool_name=tool_call.tool_name,
                success=False,
                summary=f"工具执行失败：{tool_call.tool_name}（{type(exc).__name__}: {str(exc)[:240]}）",
                error=f"{type(exc).__name__}: {exc}",
            )


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}
