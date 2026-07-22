"""Tool registry and runtime context for the V3 Agent Kernel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from backend.app.agent_kernel.models import KernelObservation, ToolCall, ToolSpec
from backend.app.agent_state.models import SectorBreakerState
from backend.app.providers.interfaces import (
    ContentExtractionProvider,
    LLMProvider,
    SearchProvider,
    SourceVerificationProvider,
)
from backend.app.schemas import Artifact, ResearchProject, RunEvent
from backend.app.storage.sqlite import SQLiteRepository

if TYPE_CHECKING:
    from backend.app.rag import ProjectRetriever


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
    content_extraction_provider: ContentExtractionProvider | None = None
    source_verification_provider: SourceVerificationProvider | None = None
    artifacts: list[Artifact] = field(default_factory=list)
    initial_artifact_ids: set[str] = field(default_factory=set)
    run_id: str | None = None
    search_call_count: int = 0
    provider_request_count: int = 0
    extraction_request_count: int = 0
    max_provider_requests: int = 32
    max_extraction_requests: int = 12
    writer_call_count: int = 0
    project_retriever: "ProjectRetriever | None" = None
    # Optional callback: called after each successful artifact write for checkpointing
    on_artifact_written: Callable[[str, int], Awaitable[None]] | None = None

    def consume_search_call(self) -> None:
        self.search_call_count += 1
        self.state.run_budget_usage.search_calls = self.search_call_count

    def consume_provider_requests(self, count: int) -> None:
        if count < 0:
            raise ValueError("provider request count cannot be negative")
        self.provider_request_count += count
        self.state.run_budget_usage.provider_requests = self.provider_request_count

    def consume_extraction_request(self) -> None:
        self.extraction_request_count += 1
        self.state.run_budget_usage.extraction_requests = self.extraction_request_count

    def consume_writer_call(self) -> None:
        self.writer_call_count += 1
        self.state.run_budget_usage.writer_calls = self.writer_call_count

    def new_artifacts(self) -> list[Artifact]:
        return [artifact for artifact in self.artifacts if artifact.id not in self.initial_artifact_ids]

    def has_current_run_output(self) -> bool:
        return bool(self.new_artifacts()) or bool(
            self.run_id
            and any(artifact.run_id == self.run_id for artifact in self.artifacts)
        )


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
