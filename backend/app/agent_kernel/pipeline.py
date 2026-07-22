"""Production entry point for the V3 knowledge-management Agent Kernel."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from backend.app.agent_kernel.models import KernelLoopConfig, KernelRunResult, KernelRunStatus
from backend.app.agent_kernel.policy import LLMAgentPolicy
from backend.app.agent_kernel.runtime import AgentKernelRuntime
from backend.app.agent_kernel.schema_planner import build_adaptive_schema
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools import build_default_tool_registry
from backend.app.agent_state import ArtifactMemory, ReportInternalizer, SectorBreakerState
from backend.app.agent_state.models import AgentAction, AgentDecision
from backend.app.providers.interfaces import (
    ContentExtractionProvider,
    LLMProvider,
    SearchProvider,
    SourceVerificationProvider,
)
from backend.app.rag import ProjectRetriever
from backend.app.schemas import (
    Artifact,
    MaintenanceRunRequest,
    ProjectDocumentCreate,
    ResearchProject,
    ResumeRequest,
    RunEvent,
)
from backend.app.storage.sqlite import SQLiteRepository


async def run_v2_agent_kernel_pipeline(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    content_extraction_provider: ContentExtractionProvider | None = None,
    source_verification_provider: SourceVerificationProvider | None = None,
    emit: Callable[[RunEvent], Awaitable[None]] | None = None,
    run_id: str | None = None,
    resume_state: SectorBreakerState | None = None,
    resume_request: ResumeRequest | None = None,
    maintenance_request: MaintenanceRunRequest | None = None,
    project_retriever: ProjectRetriever | None = None,
) -> KernelRunResult:
    """Run the Agent Kernel, persist durable outputs, and return its terminal status."""

    async def emit_event(event: RunEvent) -> None:
        if emit is not None:
            await emit(event)

    _run_id = run_id or project.id

    if resume_state is not None:
        state = resume_state
        state.state_version = "3"
        if resume_request is None:
            state.meta_context.source_pack_ids = list(project.source_preferences.source_pack_ids)
            state.meta_context.source_enforcement = project.source_preferences.enforcement.value
            state.meta_context.custom_allowed_domains = list(project.source_preferences.custom_allowed_domains)
            state.meta_context.blocked_domains = list(project.source_preferences.blocked_domains)
        await emit_event(RunEvent(
            event_type="node_started",
            gate="initialize_state",
            agent="V3 Agent Kernel",
            message=(
                "Resuming from existing State checkpoint: "
                + str(len(state.shared_knowledge.source_memories)) + " sources, "
                + str(len(state.shared_knowledge.claims)) + " claims, "
                + str(len(state.evidence_refs)) + " evidence refs."
            ),
            data={
                "pipeline": "agent_kernel",
                "schema_version": "v3-knowledge-ops",
                "resumed": True,
                "knowledge_schema_strategy": state.knowledge_schema.strategy,
            },
        ))
        if resume_request is not None:
            feedback_items = _resume_feedback_items(resume_request)
            state.human_feedback.extend(feedback_items)
            new_document_ids: set[str] = set()
            if resume_request.assistant_brief and resume_request.assistant_brief.strip():
                document = repository.add_document(
                    project.id,
                    ProjectDocumentCreate(
                        channel="assistant_brief",
                        content=resume_request.assistant_brief.strip(),
                        file_name=f"resume-{_run_id}-assistant-brief.md",
                        mime_type="text/markdown",
                    ),
                )
                new_document_ids.add(document.id)
            if new_document_ids:
                await _internalize_uploaded_documents(
                    project=project,
                    repository=repository,
                    state=state,
                    emit_event=emit_event,
                    document_ids=new_document_ids,
                )
            await emit_event(RunEvent(
                event_type="node_completed",
                gate="human_feedback",
                agent="V3 Agent Kernel",
                message=f"已消费用户反馈 {len(feedback_items)} 项，并恢复 Agent 决策。",
                data={"feedback_count": len(feedback_items), "document_ids": sorted(new_document_ids)},
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
            source_pack_ids=project.source_preferences.source_pack_ids,
            source_enforcement=project.source_preferences.enforcement.value,
            custom_allowed_domains=project.source_preferences.custom_allowed_domains,
            blocked_domains=project.source_preferences.blocked_domains,
            knowledge_schema=knowledge_schema,
        )
        await emit_event(RunEvent(
            event_type="node_started",
            gate="initialize_state",
            agent="V3 Agent Kernel",
            message="Agent Kernel started: using State + Tools + ReAct loop.",
            data={
                "pipeline": "agent_kernel",
                "schema_version": "v3-knowledge-ops",
                "knowledge_schema_strategy": state.knowledge_schema.strategy,
                "knowledge_schema_reason": state.knowledge_schema.generated_reason,
                "source_preferences": project.source_preferences.model_dump(mode="json"),
                "state": state.model_dump(mode="json"),
            },
        ))
        await _internalize_uploaded_documents(
            project=project,
            repository=repository,
            state=state,
            emit_event=emit_event,
        )

    if maintenance_request is not None:
        latest_import = repository.latest_vault_import(project.id)
        latest_health = repository.latest_health_report(project.id)
        state.vault_import_id = latest_import.id if latest_import else state.vault_import_id
        state.latest_health_report_id = latest_health.id if latest_health else state.latest_health_report_id
        state.active_maintenance_objective = maintenance_request.objective.strip()
        state.maintenance_task_ids = list(dict.fromkeys(maintenance_request.task_ids))
        selected_tasks = [
            task for task in repository.list_maintenance_tasks(project.id)
            if task.id in state.maintenance_task_ids
        ]
        state.maintenance_task_summaries = [
            f"{task.id} | {task.task_type} | {task.objective} | paths={','.join(task.target_paths)}"
            for task in selected_tasks
        ]
        policy_data = {
            **state.autonomy_policy.model_dump(),
            **maintenance_request.autonomy_policy,
            "execution_mode": maintenance_request.execution_mode,
        }
        state.autonomy_policy = state.autonomy_policy.model_validate(policy_data)
        if state.active_maintenance_objective:
            state.meta_context.user_goal = state.active_maintenance_objective

    # A same-run human resume keeps consumed budgets. A new run starts with a
    # fresh budget even when it restores project knowledge from a checkpoint.
    if resume_request is None:
        state.run_budget_usage = state.run_budget_usage.model_validate({})

    registry = build_default_tool_registry()
    active_artifacts = repository.list_artifacts(project.id)
    initial_artifact_ids = {artifact.id for artifact in active_artifacts}
    _sync_artifact_memory(state, active_artifacts)

    # Forward-declare so the closure can reference runtime_context after creation
    _runtime_context_holder: list[KernelRuntimeContext] = []

    async def _checkpoint_on_artifact(artifact_id: str, iteration: int) -> None:
        ctx = _runtime_context_holder[0] if _runtime_context_holder else None
        if ctx is None:
            return
        artifact = next((item for item in ctx.artifacts if item.id == artifact_id), None)
        if artifact is None:
            return
        repository.add_artifact(artifact)
        _sync_artifact_memory(ctx.state, repository.list_artifacts(project.id))
        repository.save_run_state_checkpoint(
            run_id=_run_id,
            project_id=project.id,
            state=ctx.state,
            checkpoint_type="artifact_write",
            artifact_id=artifact_id,
            iteration=iteration,
        )

    runtime_context = KernelRuntimeContext(
        project=project,
        repository=repository,
        state=state,
        search_provider=search_provider,
        llm_provider=llm_provider,
        emit_event=emit_event,
        content_extraction_provider=content_extraction_provider,
        source_verification_provider=source_verification_provider,
        artifacts=list(active_artifacts),
        initial_artifact_ids=initial_artifact_ids,
        run_id=_run_id,
        search_call_count=state.run_budget_usage.search_calls,
        provider_request_count=state.run_budget_usage.provider_requests,
        extraction_request_count=state.run_budget_usage.extraction_requests,
        writer_call_count=state.run_budget_usage.writer_calls,
        project_retriever=project_retriever,
        on_artifact_written=_checkpoint_on_artifact,
    )
    _runtime_context_holder.append(runtime_context)

    loop_config = _kernel_config_for_project(project)
    loop_config.max_search_calls = min(loop_config.max_search_calls, state.autonomy_policy.max_search_calls)
    loop_config.max_provider_requests = min(loop_config.max_provider_requests, state.autonomy_policy.max_provider_requests)
    loop_config.max_extraction_requests = min(loop_config.max_extraction_requests, state.autonomy_policy.max_extraction_requests)
    loop_config.max_writer_calls = min(loop_config.max_writer_calls, state.autonomy_policy.max_writer_calls)
    state.autonomy_policy.max_search_calls = loop_config.max_search_calls
    state.autonomy_policy.max_provider_requests = loop_config.max_provider_requests
    state.autonomy_policy.max_extraction_requests = loop_config.max_extraction_requests
    state.autonomy_policy.max_writer_calls = loop_config.max_writer_calls
    runtime_context.max_provider_requests = loop_config.max_provider_requests
    runtime_context.max_extraction_requests = loop_config.max_extraction_requests
    runtime = AgentKernelRuntime(
        policy=LLMAgentPolicy(llm_provider),
        registry=registry,
        config=loop_config,
    )
    result = await runtime.run(runtime_context)

    # Save final state for either continuation or diagnostics.
    new_artifacts = [
        artifact for artifact in runtime_context.artifacts
        if artifact.id not in runtime_context.initial_artifact_ids
    ]
    final_checkpoint_type = "run_end_completed" if result.status == KernelRunStatus.COMPLETED else (
        "run_end_partial" if new_artifacts else "run_end"
    )

    # Durable Artifact revisions must exist before a checkpoint references the
    # final State. The per-artifact callback normally persists them earlier;
    # this idempotent pass is the hard safety boundary if that callback failed.
    for artifact in new_artifacts:
        repository.add_artifact(artifact)
    if new_artifacts:
        _sync_artifact_memory(runtime_context.state, repository.list_artifacts(project.id))
    repository.save_run_state_checkpoint(
        run_id=_run_id,
        project_id=project.id,
        state=runtime_context.state,
        checkpoint_type=final_checkpoint_type,
        iteration=result.iterations,
    )

    await emit_event(RunEvent(
        event_type="node_completed" if result.status == KernelRunStatus.COMPLETED else "node_degraded",
        gate="export" if result.status == KernelRunStatus.COMPLETED else "agent_decide",
        agent="V3 Agent Kernel",
        message="Agent Kernel run finished: " + result.status.value + ". " + result.stop_reason,
        severity="info" if result.status == KernelRunStatus.COMPLETED else "warning",
        data=result.model_dump(mode="json"),
    ))
    if new_artifacts:
        if result.failed_writes:
            await emit_event(RunEvent(
                event_type="node_degraded",
                gate="artifact_writing",
                agent="V3 Agent Kernel",
                message=(
                    "本轮已生成 "
                    + str(len(new_artifacts))
                    + " 篇文档；"
                    + str(len(result.failed_writes))
                    + " 项写作未成功，可在下一轮继续补全。"
                ),
                severity="warning",
                data={"failed_writes": result.failed_writes},
            ))
        return result
    if result.status == KernelRunStatus.WAITING_FOR_HUMAN:
        return result
    if result.status != KernelRunStatus.COMPLETED:
        raise RuntimeError("V3 Agent Kernel produced no artifacts: " + result.status.value + " / " + result.stop_reason)
    return result


def _sync_artifact_memory(state: SectorBreakerState, artifacts: list[Artifact]) -> None:
    state.artifact_memory = [
        ArtifactMemory(
            artifact_id=artifact.id,
            content_path=artifact.content_path,
            title=artifact.title,
            revision=artifact.revision,
            content_hash=artifact.content_hash,
            active=artifact.active,
            supersedes=artifact.supersedes,
            superseded_by=artifact.superseded_by,
            last_modified_run_id=artifact.run_id,
        )
        for artifact in artifacts
    ]


def _kernel_config_for_project(project: ResearchProject) -> KernelLoopConfig:
    env_config = _kernel_config_from_env()
    if env_config is not None:
        return env_config
    if project.depth.value == "deep":
        return KernelLoopConfig(max_iterations=56, max_search_calls=24, max_provider_requests=64, max_extraction_requests=24, max_writer_calls=28)
    if project.depth.value == "standard":
        return KernelLoopConfig(max_iterations=44, max_search_calls=20, max_provider_requests=48, max_extraction_requests=20, max_writer_calls=22)
    return KernelLoopConfig(max_iterations=36, max_search_calls=16, max_provider_requests=32, max_extraction_requests=12, max_writer_calls=16)


def _kernel_config_from_env() -> KernelLoopConfig | None:
    keys = {
        "max_iterations": "SECTORBREAKER_KERNEL_MAX_ITERATIONS",
        "max_search_calls": "SECTORBREAKER_KERNEL_MAX_SEARCH_CALLS",
        "max_provider_requests": "SECTORBREAKER_KERNEL_MAX_PROVIDER_REQUESTS",
        "max_extraction_requests": "SECTORBREAKER_KERNEL_MAX_EXTRACTION_REQUESTS",
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
    document_ids: set[str] | None = None,
) -> None:
    documents = repository.list_documents(project.id)
    if document_ids is not None:
        documents = [document for document in documents if document.id in document_ids]
    if not documents:
        await emit_event(RunEvent(
            event_type="node_progress",
            gate="external_materials",
            agent="V3 Agent Kernel",
            message="No uploaded materials found; Agent starts from current State and search tools.",
        ))
        return
    internalizer = ReportInternalizer()
    await emit_event(RunEvent(
        event_type="node_started",
        gate="external_materials",
        agent="V3 Report Internalizer",
        message="Writing uploaded materials into Agent State: " + str(len(documents)) + " documents.",
    ))
    for document in documents:
        report = internalizer.internalize(document, domain=project.domain)
        internalizer.apply_to_state(state, report)
        await emit_event(RunEvent(
            event_type="node_progress",
            gate="external_materials",
            agent="V3 Report Internalizer",
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


def _resume_feedback_items(request: ResumeRequest) -> list[str]:
    items: list[str] = []
    for label, value in (
        ("guidance", request.guidance),
        ("evidence_data", request.evidence_data),
        ("assistant_brief", request.assistant_brief),
    ):
        cleaned = str(value or "").strip()
        if cleaned:
            items.append(f"{label}: {cleaned[:12000]}")
    if request.plan_confirmed:
        items.append("plan_confirmed: true")
    return items
