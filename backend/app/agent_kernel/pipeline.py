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
    run_id: str | None = None,
    resume_state: SectorBreakerState | None = None,
) -> list[Artifact]:
    """Run the real V2 Agent Kernel loop and persist generated artifacts."""

    async def emit_event(event: RunEvent) -> None:
        if emit is not None:
            await emit(event)

    _run_id = run_id or project.id

    if resume_state is not None:
        state = resume_state
        await emit_event(RunEvent(
            event_type="node_started",
            gate="initialize_state",
            agent="V2 Agent Kernel",
            message=(
                "Resuming from existing State checkpoint: "
                + str(len(state.shared_knowledge.source_memories)) + " sources, "
                + str(len(state.shared_knowledge.claims)) + " claims, "
                + str(len(state.evidence_refs)) + " evidence refs."
            ),
            data={
                "pipeline": "agent_kernel",
                "schema_version": "v2-agent-kernel",
                "resumed": True,
                "knowledge_schema_strategy": state.knowledge_schema.strategy,
            },
        ))
    else:
        _user_goal = "Build a sustainable Obsidian knowledge base for: " + project.domain
        knowledge_schema = await build_adaptive_schema(
            domain=project.domain,
            user_goal=_user_goal,
            market_scope=project.market_scope.value,
            source_policy=project.source_policy.value,
            llm_provider=llm_provider,
        )
        state = SectorBreakerState.initialize(
            project_id=project.id,
            domain=project.domain,
            user_goal=_user_goal,
            market_scope=project.market_scope.value,
            source_policy=project.source_policy.value,
            knowledge_schema=knowledge_schema,
        )
        await emit_event(RunEvent(
            event_type="node_started",
            gate="initialize_state",
            agent="V2 Agent Kernel",
            message="Agent Kernel started: using State + Tools + ReAct loop.",
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

    # Forward-declare so the closure can reference runtime_context after creation
    _runtime_context_holder: list[KernelRuntimeContext] = []

    async def _checkpoint_on_artifact(artifact_id: str, iteration: int) -> None:
        ctx = _runtime_context_holder[0] if _runtime_context_holder else None
        if ctx is None:
            return
        try:
            repository.save_run_state_checkpoint(
                run_id=_run_id,
                project_id=project.id,
                state=ctx.state,
                checkpoint_type="artifact_write",
                artifact_id=artifact_id,
                iteration=iteration,
            )
        except Exception:
            pass

    runtime_context = KernelRuntimeContext(
        project=project,
        repository=repository,
        state=state,
        search_provider=search_provider,
        llm_provider=llm_provider,
        emit_event=emit_event,
        on_artifact_written=_checkpoint_on_artifact,
    )
    _runtime_context_holder.append(runtime_context)

    runtime = AgentKernelRuntime(
        policy=LLMAgentPolicy(llm_provider),
        registry=registry,
        config=_kernel_config_for_project(project),
    )
    result = await runtime.run(runtime_context)

    # Save final state for either continuation or diagnostics.
    final_checkpoint_type = (
        "run_end_completed"
        if result.status == KernelRunStatus.COMPLETED or runtime_context.artifacts
        else "run_end"
    )
    try:
        repository.save_run_state_checkpoint(
            run_id=_run_id,
            project_id=project.id,
            state=runtime_context.state,
            checkpoint_type=final_checkpoint_type,
            iteration=result.iterations,
        )
    except Exception:
        pass

    await emit_event(RunEvent(
        event_type="node_completed" if result.status == KernelRunStatus.COMPLETED else "node_degraded",
        gate="export" if result.status == KernelRunStatus.COMPLETED else "agent_decide",
        agent="V2 Agent Kernel",
        message="Agent Kernel run finished: " + result.status.value + ". " + result.stop_reason,
        severity="info" if result.status == KernelRunStatus.COMPLETED else "warning",
        data=result.model_dump(mode="json"),
    ))
    for artifact in runtime_context.artifacts:
        repository.add_artifact(artifact)
    if runtime_context.artifacts:
        if result.failed_writes:
            await emit_event(RunEvent(
                event_type="node_degraded",
                gate="artifact_writing",
                agent="V2 Agent Kernel",
                message=(
                    "本轮已生成 "
                    + str(len(runtime_context.artifacts))
                    + " 篇文档；"
                    + str(len(result.failed_writes))
                    + " 项写作未成功，可在下一轮继续补全。"
                ),
                severity="warning",
                data={"failed_writes": result.failed_writes},
            ))
        return runtime_context.artifacts
    if result.status != KernelRunStatus.COMPLETED:
        raise RuntimeError("V2 Agent Kernel produced no artifacts: " + result.status.value + " / " + result.stop_reason)
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
            message="No uploaded materials found; Agent starts from current State and search tools.",
        ))
        return
    internalizer = ReportInternalizer()
    await emit_event(RunEvent(
        event_type="node_started",
        gate="external_materials",
        agent="V2 Report Internalizer",
        message="Writing uploaded materials into Agent State: " + str(len(documents)) + " documents.",
    ))
    for document in documents:
        report = internalizer.internalize(document, domain=project.domain)
        internalizer.apply_to_state(state, report)
        await emit_event(RunEvent(
            event_type="node_progress",
            gate="external_materials",
            agent="V2 Report Internalizer",
            message=(
                "Internalized: " + (document.file_name or document.id)
                + ", claims=" + str(len(report.claims))
                + ", entities=" + str(len(report.entities))
                + ", questions=" + str(len(report.open_questions))
            ),
            data=report.model_dump(mode="json"),
        ))
    state.add_decision(AgentDecision(
        action=AgentAction.CONTINUE,
        reason="Uploaded materials have been internalized into Agent State. Subsequent searches should supplement, not blindly re-search.",
    ))
