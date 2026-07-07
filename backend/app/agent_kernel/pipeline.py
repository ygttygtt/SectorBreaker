"""Production entry point for the V2 Agent Kernel personal knowledge path."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from backend.app.agent_kernel.models import KernelLoopConfig, KernelRunStatus
from backend.app.agent_kernel.policy import LLMAgentPolicy
from backend.app.agent_kernel.runtime import AgentKernelRuntime
from backend.app.agent_kernel.schema_planner import build_adaptive_schema
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools import build_default_tool_registry
from backend.app.agent_state import ReportInternalizer, SectorBreakerState
from backend.app.agent_state.models import AgentAction, AgentDecision
from backend.app.providers.interfaces import LLMProvider, SearchProvider
from backend.app.schemas import Artifact, ResearchProject, RunEvent
from backend.app.storage.sqlite import SQLiteRepository


async def run_v2_agent_kernel_pipeline(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    emit: Callable[[RunEvent], Awaitable[None]] | None = None,
) -> list[Artifact]:
    """Run the real V2 Agent Kernel loop and persist generated artifacts."""

    async def emit_event(event: RunEvent) -> None:
        if emit is not None:
            await emit(event)

    knowledge_schema = await build_adaptive_schema(
        domain=project.domain,
        user_goal=f"为“{project.domain}”构建可持续扩展的 Obsidian 领域知识库",
        market_scope=project.market_scope.value,
        source_policy=project.source_policy.value,
        llm_provider=llm_provider,
    )
    state = SectorBreakerState.initialize(
        project_id=project.id,
        domain=project.domain,
        user_goal=f"为“{project.domain}”构建可持续扩展的 Obsidian 领域知识库",
        market_scope=project.market_scope.value,
        source_policy=project.source_policy.value,
        knowledge_schema=knowledge_schema,
    )
    await emit_event(RunEvent(
        event_type="node_started",
        gate="initialize_state",
        agent="V2 Agent Kernel",
        message="Agent Kernel 已启动：本轮使用 State + Tools + ReAct 主循环，不再执行旧 L1-L5 固定 workflow。",
        data={
            "pipeline": "agent_kernel",
            "schema_version": "v2-agent-kernel",
            "knowledge_schema_strategy": state.knowledge_schema.strategy,
            "knowledge_schema_reason": state.knowledge_schema.generated_reason,
            "state": state.model_dump(mode="json"),
        },
    ))
    await _internalize_uploaded_documents(
        project=project,
        repository=repository,
        state=state,
        emit_event=emit_event,
    )
    registry = build_default_tool_registry()
    runtime_context = KernelRuntimeContext(
        project=project,
        repository=repository,
        state=state,
        search_provider=search_provider,
        llm_provider=llm_provider,
        emit_event=emit_event,
    )
    runtime = AgentKernelRuntime(
        policy=LLMAgentPolicy(llm_provider),
        registry=registry,
        config=_kernel_config_for_project(project),
    )
    result = await runtime.run(runtime_context)
    await emit_event(RunEvent(
        event_type="node_completed" if result.status == KernelRunStatus.COMPLETED else "node_degraded",
        gate="export" if result.status == KernelRunStatus.COMPLETED else "agent_decide",
        agent="V2 Agent Kernel",
        message=f"Agent Kernel 运行结束：{result.status.value}。{result.stop_reason}",
        severity="info" if result.status == KernelRunStatus.COMPLETED else "warning",
        data=result.model_dump(mode="json"),
    ))
    if result.status != KernelRunStatus.COMPLETED:
        raise RuntimeError(f"V2 Agent Kernel 未能完成：{result.status.value} / {result.stop_reason}")
    for artifact in runtime_context.artifacts:
        repository.add_artifact(artifact)
    return runtime_context.artifacts


def _kernel_config_for_project(project: ResearchProject) -> KernelLoopConfig:
    env_config = _kernel_config_from_env()
    if env_config is not None:
        return env_config
    if project.depth.value == "deep":
        return KernelLoopConfig(max_iterations=56, max_search_calls=24, max_writer_calls=28)
    if project.depth.value == "standard":
        return KernelLoopConfig(max_iterations=44, max_search_calls=20, max_writer_calls=22)
    return KernelLoopConfig(max_iterations=36, max_search_calls=16, max_writer_calls=16)


def _kernel_config_from_env() -> KernelLoopConfig | None:
    keys = {
        "max_iterations": "SECTORBREAKER_KERNEL_MAX_ITERATIONS",
        "max_search_calls": "SECTORBREAKER_KERNEL_MAX_SEARCH_CALLS",
        "max_writer_calls": "SECTORBREAKER_KERNEL_MAX_WRITER_CALLS",
    }
    values = {}
    for field, key in keys.items():
        raw = os.getenv(key)
        if raw is None:
            continue
        try:
            values[field] = int(raw)
        except ValueError:
            continue
    return KernelLoopConfig(**values) if values else None


async def _internalize_uploaded_documents(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    state: SectorBreakerState,
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> None:
    documents = repository.list_documents(project.id)
    if not documents:
        await emit_event(RunEvent(
            event_type="node_progress",
            gate="external_materials",
            agent="V2 Agent Kernel",
            message="未发现上传外部材料，Agent 将从当前 State 和搜索工具开始。",
        ))
        return
    internalizer = ReportInternalizer()
    await emit_event(RunEvent(
        event_type="node_started",
        gate="external_materials",
        agent="V2 Report Internalizer",
        message=f"正在把上传材料写入 Agent State：{len(documents)} 个文档。",
    ))
    for document in documents:
        report = internalizer.internalize(document, domain=project.domain)
        internalizer.apply_to_state(state, report)
        await emit_event(RunEvent(
            event_type="node_progress",
            gate="external_materials",
            agent="V2 Report Internalizer",
            message=(
                f"已内化上传材料：{document.file_name or document.id}，"
                f"claims={len(report.claims)}，entities={len(report.entities)}，questions={len(report.open_questions)}"
            ),
            data=report.model_dump(mode="json"),
        ))
    state.add_decision(AgentDecision(
        action=AgentAction.CONTINUE,
        reason="上传材料已进入 Agent Kernel State。后续搜索应作为补充、验证或下钻，而不是盲目重搜。",
    ))
