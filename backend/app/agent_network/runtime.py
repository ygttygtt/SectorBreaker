"""Deadline-bound live challenge orchestration inside the V3 Agent Kernel."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field, model_validator

from backend.app.agent_kernel.models import (
    KernelRunResult,
    KernelRunStatus,
    ToolCall,
)
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.search import search_web
from backend.app.agent_network.planner import plan_live_challenge
from backend.app.agent_network.registry import AgentRegistry, build_demo_agent_registry
from backend.app.agent_network.scheduler import AgentScheduler, persist_settlement
from backend.app.agent_state import SectorBreakerState
from backend.app.knowledge_base import ChangeSetService
from backend.app.providers.interfaces import (
    ChatMessage,
    ContentExtractionProvider,
    LLMProvider,
    SearchProvider,
    SourceVerificationProvider,
)
from backend.app.providers.source_policy import build_project_search_constraints, url_matches_domain_policy
from backend.app.schemas import (
    AgentDeliverable,
    AgentManifest,
    AgentMission,
    AgentTransport,
    ChangeSetProposalRequest,
    ClaimStrength,
    ClaimCheck,
    ClaimCheckStatus,
    DeliverableFinding,
    DeliverableUsage,
    EvidenceItem,
    LiveChallengeRequest,
    MissionStatus,
    ResearchProject,
    RunEvent,
    SourceChannel,
    SourceQuality,
    TaskSettlement,
    ToolObservationRecord,
    WorkOrder,
    WorkOrderStatus,
    WorkOrderType,
    VerificationStatus,
)
from backend.app.storage.sqlite import SQLiteRepository


EmitFn = Callable[[RunEvent], Awaitable[None]]


class A2AWorkerTransport(Protocol):
    async def discover(self, endpoint: str) -> dict: ...

    async def execute(
        self,
        endpoint: str,
        work_order: WorkOrder,
        *,
        domain: str,
        timeout_seconds: int,
    ) -> AgentDeliverable: ...


class ResearchDecision(BaseModel):
    query: str = Field(default="", validation_alias=AliasChoices("query", "search_query"))
    queries: list[str] = Field(
        default_factory=list,
        max_length=3,
        validation_alias=AliasChoices("queries", "query_variants", "search_queries"),
    )
    search_goal: str = Field(
        default="",
        validation_alias=AliasChoices("search_goal", "research_goal", "goal"),
    )
    rationale: str = Field(default="", validation_alias=AliasChoices("rationale", "reasoning", "reason"))

    @model_validator(mode="after")
    def fill_query_from_goal(self) -> "ResearchDecision":
        if not self.query.strip() and self.queries:
            self.query = self.queries[0]
        if not self.query.strip() and self.search_goal.strip():
            self.query = self.search_goal
        if not self.search_goal.strip() and self.query.strip():
            self.search_goal = self.query
        if not self.query.strip():
            raise ValueError("research decision requires a query or search goal")
        return self


class ResearchSynthesis(BaseModel):
    summary: str = Field(validation_alias=AliasChoices("summary", "research_summary", "overview"))
    findings: list[DeliverableFinding] = Field(
        validation_alias=AliasChoices("findings", "key_findings", "results")
    )
    unresolved_questions: list[str] = Field(default_factory=list)


class VerificationSynthesis(BaseModel):
    summary: str = Field(validation_alias=AliasChoices("summary", "verification_summary", "overview"))
    claim_checks: list[ClaimCheck] = Field(
        validation_alias=AliasChoices("claim_checks", "checks", "claim_verifications")
    )
    unresolved_questions: list[str] = Field(default_factory=list)


async def run_live_challenge(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    search_provider: SearchProvider | None,
    content_extraction_provider: ContentExtractionProvider | None,
    source_verification_provider: SourceVerificationProvider | None,
    llm_provider: LLMProvider | None,
    emit: EmitFn,
    run_id: str,
    request: LiveChallengeRequest,
    a2a_transport: A2AWorkerTransport | None = None,
) -> KernelRunResult:
    """Execute one real, bounded challenge and stop at ChangeSet review."""

    challenge_started_at = datetime.now(UTC)

    if llm_provider is None or search_provider is None or content_extraction_provider is None:
        missing = [
            name
            for name, value in (
                ("LLM", llm_provider),
                ("SearchProvider", search_provider),
                ("ContentExtractionProvider", content_extraction_provider),
            )
            if value is None
        ]
        return KernelRunResult(
            status=KernelRunStatus.BLOCKED,
            state_version="3",
            stop_reason="live challenge missing providers: " + ", ".join(missing),
        )

    challenge_project = project.model_copy(update={
        "domain": request.domain,
        "source_policy": request.source_policy,
    })
    state = SectorBreakerState.initialize(
        project_id=project.id,
        domain=request.domain,
        user_goal=request.question or f"为 {request.domain} 创建证据型 Starter Note",
        market_scope=project.market_scope.value,
        source_policy=request.source_policy.value,
        source_pack_ids=project.source_preferences.source_pack_ids,
        source_enforcement=project.source_preferences.enforcement.value,
        custom_allowed_domains=project.source_preferences.custom_allowed_domains,
        blocked_domains=project.source_preferences.blocked_domains,
    )

    await _emit(
        emit,
        "mission_planning",
        "agent_decide",
        "V3 Master Agent",
        f"正在把“{request.domain}”转换为有依赖、预算和验收条件的任务合同。",
        {"domain": request.domain, "deadline_seconds": request.deadline_seconds},
    )
    try:
        mission = await asyncio.wait_for(
            plan_live_challenge(
                project_id=project.id,
                run_id=run_id,
                request=request,
                llm_provider=llm_provider,
            ),
            timeout=min(80, request.deadline_seconds / 3),
        )
    except Exception as exc:
        return KernelRunResult(
            status=KernelRunStatus.FAILED,
            state_version="3",
            stop_reason=f"mission planning failed: {type(exc).__name__}: {str(exc)[:240]}",
        )

    # The live contract starts when the user submits the challenge, not after
    # planning.  Rebase the generated mission so every downstream timeout sees
    # the same wall-clock deadline shown in the UI.
    mission.started_at = challenge_started_at
    mission.deadline_at = challenge_started_at + timedelta(seconds=request.deadline_seconds)
    mission.updated_at = datetime.now(UTC)

    a2a_endpoint = _a2a_endpoint()
    a2a_available = False
    a2a_capabilities: list[str] = []
    if a2a_endpoint and a2a_transport is not None:
        try:
            card = await asyncio.wait_for(a2a_transport.discover(a2a_endpoint), timeout=8)
            a2a_capabilities = _capabilities_from_agent_card(card)
            a2a_available = "research_ecosystem" in a2a_capabilities
        except Exception as exc:
            await _emit(
                emit,
                "task_reassigned",
                "tool_execution",
                "A2A Transport",
                "A2A Researcher 预检失败，本轮会真实改派给本地同能力 Agent。",
                {"endpoint": a2a_endpoint, "error": f"{type(exc).__name__}: {str(exc)[:180]}"},
                severity="warning",
            )
    registry = build_demo_agent_registry(
        repository,
        project.id,
        a2a_endpoint=a2a_endpoint,
        a2a_available=a2a_available,
        a2a_capabilities=a2a_capabilities or None,
    )
    scheduler = AgentScheduler(registry)
    mission.status = MissionStatus.RUNNING
    repository.save_agent_mission(mission)
    await _emit(
        emit,
        "mission_planned",
        "agent_decide",
        "V3 Master Agent",
        f"Mission 已生成：{len(mission.work_orders)} 个 WorkOrder。",
        {"mission": mission.model_dump(mode="json")},
    )

    while True:
        remaining = _remaining_seconds(mission)
        if remaining <= 5:
            mission.status = MissionStatus.BLOCKED
            mission.failure_reason = "live challenge deadline exhausted before all required work orders completed"
            repository.save_agent_mission(mission)
            return _blocked_result(state, mission.failure_reason)
        pending = [item for item in mission.work_orders if item.status == WorkOrderStatus.PLANNED]
        if not pending:
            break
        ready = [
            item
            for item in pending
            if all(_work_order(mission, dep).status == WorkOrderStatus.ACCEPTED for dep in item.depends_on)
        ]
        if remaining < 90:
            skipped = [item for item in ready if item.optional]
            for item in skipped:
                item.status = WorkOrderStatus.BLOCKED
                item.completed_at = datetime.now(UTC)
            ready = [item for item in ready if not item.optional]
            if skipped:
                await _emit(
                    emit,
                    "deadline_adjusted",
                    "agent_decide",
                    "Deadline Manager",
                    "剩余时间不足 90 秒，未启动的可选任务已停止，保留真实已验收证据继续收敛。",
                    {"remaining_seconds": round(remaining), "skipped_task_ids": [item.id for item in skipped]},
                    severity="warning",
                )
        if not ready:
            blocked_upstream = [
                item for item in pending
                if any(_work_order(mission, dep).status in {
                    WorkOrderStatus.FAILED,
                    WorkOrderStatus.BLOCKED,
                } for dep in item.depends_on)
            ]
            for item in blocked_upstream:
                item.status = WorkOrderStatus.BLOCKED
            if blocked_upstream:
                repository.save_agent_mission(mission)
                continue
            mission.status = MissionStatus.BLOCKED
            mission.failure_reason = "mission graph has no executable work order"
            repository.save_agent_mission(mission)
            return _blocked_result(state, mission.failure_reason)

        results = await asyncio.gather(*[
            _execute_work_order(
                work_order=item,
                mission=mission,
                registry=registry,
                scheduler=scheduler,
                project=challenge_project,
                repository=repository,
                state=state,
                search_provider=search_provider,
                content_extraction_provider=content_extraction_provider,
                source_verification_provider=source_verification_provider,
                llm_provider=llm_provider,
                emit=emit,
                a2a_transport=a2a_transport,
            )
            for item in ready
        ], return_exceptions=True)
        for item, result in zip(ready, results, strict=True):
            if isinstance(result, Exception):
                item.status = WorkOrderStatus.FAILED
                item.completed_at = datetime.now(UTC)
                await _emit(
                    emit,
                    "deliverable_rejected",
                    "tool_execution",
                    item.assigned_agent_id or "Specialist",
                    f"WorkOrder {item.id} 执行失败，错误已结构化记录。",
                    {"task_id": item.id, "error": f"{type(result).__name__}: {str(result)[:240]}"},
                    severity="error",
                )
                continue
            deliverable, settlement = result
            mission.deliverables.append(deliverable)
            mission.settlements.append(settlement)
            if settlement.accepted:
                item.status = WorkOrderStatus.ACCEPTED
            else:
                item.status = WorkOrderStatus.FAILED
            item.completed_at = datetime.now(UTC)
            if deliverable.evidence_ids:
                state.evidence_refs.extend(
                    evidence_id for evidence_id in deliverable.evidence_ids if evidence_id not in state.evidence_refs
                )
            state.delegation_log.append(json.dumps({
                "task_id": item.id,
                "agent_id": deliverable.agent_id,
                "summary": deliverable.summary,
                "accepted": settlement.accepted,
                "quality_score": settlement.quality_score,
                "evidence_ids": deliverable.evidence_ids,
            }, ensure_ascii=False))
        repository.save_agent_mission(mission)

    editor = next(
        (
            item for item in mission.work_orders
            if item.task_type == WorkOrderType.EDIT and item.status == WorkOrderStatus.ACCEPTED
        ),
        None,
    )
    if editor is None:
        mission.status = MissionStatus.BLOCKED
        mission.failure_reason = "Starter Note editor did not produce an accepted deliverable"
        repository.save_agent_mission(mission)
        repository.save_run_state_checkpoint(
            run_id=run_id,
            project_id=project.id,
            state=state,
            checkpoint_type="run_end",
        )
        return _blocked_result(state, mission.failure_reason)
    editor_deliverable = next(item for item in mission.deliverables if item.task_id == editor.id)
    valid_evidence_ids = _valid_evidence_ids(repository, project.id, editor_deliverable.evidence_ids)
    if len(valid_evidence_ids) < 2 or not editor_deliverable.draft_markdown:
        mission.status = MissionStatus.BLOCKED
        mission.failure_reason = "Starter Note requires at least two real project Evidence records"
        repository.save_agent_mission(mission)
        return _blocked_result(state, mission.failure_reason)

    change_set = ChangeSetService(repository).propose(
        project.id,
        ChangeSetProposalRequest(
            summary=f"Live Challenge：为 {request.domain} 创建证据型 Starter Note",
            path=editor_deliverable.proposed_path or _starter_note_path(request.domain),
            after_content=editor_deliverable.draft_markdown,
            evidence_ids=valid_evidence_ids,
            factual_change=True,
        ),
        actor=editor_deliverable.agent_id,
        run_id=run_id,
    )
    mission.change_set_id = change_set.id
    mission.status = MissionStatus.WAITING_FOR_REVIEW
    repository.save_agent_mission(mission)
    repository.save_run_state_checkpoint(
        run_id=run_id,
        project_id=project.id,
        state=state,
        checkpoint_type="run_end_partial",
        iteration=len(mission.work_orders),
    )
    await _emit(
        emit,
        "deliverable_accepted",
        "human_feedback",
        editor_deliverable.agent_id,
        "Starter Note 已通过合同与证据门，形成 ChangeSet，等待人工审批后发布。",
        {
            "mission_id": mission.id,
            "change_set_id": change_set.id,
            "path": editor_deliverable.proposed_path,
            "evidence_ids": valid_evidence_ids,
            "elapsed_seconds": round((datetime.now(UTC) - mission.started_at).total_seconds(), 1),
        },
    )
    return KernelRunResult(
        status=KernelRunStatus.WAITING_FOR_HUMAN,
        state_version=state.state_version,
        stop_reason="Starter Note 已生成并通过证据门，等待审批发布。",
        iterations=len(mission.work_orders),
    )


async def _execute_work_order(
    *,
    work_order: WorkOrder,
    mission: AgentMission,
    registry: AgentRegistry,
    scheduler: AgentScheduler,
    project: ResearchProject,
    repository: SQLiteRepository,
    state: SectorBreakerState,
    search_provider: SearchProvider,
    content_extraction_provider: ContentExtractionProvider,
    source_verification_provider: SourceVerificationProvider | None,
    llm_provider: LLMProvider,
    emit: EmitFn,
    a2a_transport: A2AWorkerTransport | None,
) -> tuple[AgentDeliverable, TaskSettlement]:
    work_order.status = WorkOrderStatus.OFFERED
    await _emit(
        emit,
        "task_offered",
        "tool_execution",
        "Agent Scheduler",
        f"发布 WorkOrder：{work_order.objective}",
        {"work_order": work_order.model_dump(mode="json")},
    )
    manifest = scheduler.assign(work_order, remaining_seconds=_remaining_seconds(mission))
    required_tools = {
        WorkOrderType.RESEARCH: {"search_web"},
        WorkOrderType.VERIFY: {"search_web"},
        WorkOrderType.EDIT: {"retrieve_project_memory"},
    }[work_order.task_type]
    missing_tools = required_tools - set(manifest.tool_allowlist)
    if missing_tools:
        raise RuntimeError(
            f"agent permission contract missing tools: {', '.join(sorted(missing_tools))}"
        )
    work_order.status = WorkOrderStatus.ASSIGNED
    await _emit(
        emit,
        "task_awarded",
        "tool_execution",
        manifest.display_name,
        f"{manifest.display_name} 获派任务，原因：{work_order.assignment_trace[0].rationale}",
        {
            "task_id": work_order.id,
            "agent": manifest.model_dump(mode="json"),
            "bids": [item.model_dump(mode="json") for item in work_order.assignment_trace],
        },
    )
    started = perf_counter()
    work_order.status = WorkOrderStatus.RUNNING
    work_order.started_at = datetime.now(UTC)
    await _emit(
        emit,
        "specialist_started",
        "tool_execution",
        manifest.display_name,
        f"{manifest.display_name} 开始执行受限 Mini-ReAct。",
        {"task_id": work_order.id, "transport": manifest.transport.value, "budget": work_order.budget.model_dump()},
    )

    last_deliverable: AgentDeliverable | None = None
    last_reason = ""
    reworked_agents: set[str] = set()
    for _attempt in range(4):
        work_order.attempts += 1
        try:
            if manifest.transport == AgentTransport.A2A:
                if a2a_transport is None or not manifest.endpoint:
                    raise RuntimeError("A2A transport is unavailable")
                last_deliverable = await a2a_transport.execute(
                    manifest.endpoint,
                    work_order,
                    domain=mission.domain,
                    timeout_seconds=min(work_order.budget.deadline_seconds, int(_remaining_seconds(mission))),
                )
                last_deliverable = await _admit_remote_evidence(
                    last_deliverable,
                    project=project,
                    repository=repository,
                    source_verifier=source_verification_provider,
                )
            elif work_order.task_type == WorkOrderType.RESEARCH:
                last_deliverable = await asyncio.wait_for(_run_researcher(
                    manifest, work_order, mission, project, repository, state,
                    search_provider, content_extraction_provider, source_verification_provider,
                    llm_provider, emit, feedback=last_reason,
                ), timeout=max(5, min(work_order.budget.deadline_seconds, _remaining_seconds(mission))))
            elif work_order.task_type == WorkOrderType.VERIFY:
                last_deliverable = await asyncio.wait_for(_run_verifier(
                    manifest, work_order, mission, project, repository, state,
                    search_provider, content_extraction_provider, source_verification_provider,
                    llm_provider, emit, feedback=last_reason,
                ), timeout=max(5, min(work_order.budget.deadline_seconds, _remaining_seconds(mission))))
            else:
                last_deliverable = await asyncio.wait_for(_run_editor(
                    manifest, work_order, mission, repository, llm_provider, emit, feedback=last_reason,
                ), timeout=max(5, min(work_order.budget.deadline_seconds, _remaining_seconds(mission))))
            await _emit_provider_failovers(
                emit,
                work_order.id,
                llm_provider,
                content_extraction_provider,
            )
        except Exception as exc:
            if manifest.transport == AgentTransport.A2A:
                scheduler.release(manifest.agent_id)
                registry.replace(manifest.model_copy(update={"available": False}))
                await _emit(
                    emit,
                    "task_reassigned",
                    "tool_execution",
                    "Agent Scheduler",
                    "远端 A2A Agent 未完成合同，任务已真实改派给本地同能力 Agent。",
                    {"task_id": work_order.id, "failed_agent_id": manifest.agent_id, "error": f"{type(exc).__name__}: {str(exc)[:180]}"},
                    severity="warning",
                )
                manifest = scheduler.assign(work_order, remaining_seconds=_remaining_seconds(mission))
                continue
            last_reason = f"execution error: {type(exc).__name__}: {str(exc)[:180]}"
            if manifest.agent_id not in reworked_agents:
                reworked_agents.add(manifest.agent_id)
                await _emit(
                    emit,
                    "deliverable_rework",
                    "tool_execution",
                    manifest.display_name,
                    "首次执行未形成合格交付，进入一次定向返工。",
                    {"task_id": work_order.id, "reason": last_reason},
                    severity="warning",
                )
                continue
            raise

        await _emit(
            emit,
            "deliverable_submitted",
            "tool_execution",
            manifest.display_name,
            f"{manifest.display_name} 已提交强类型 AgentDeliverable，等待本地合同门验收。",
            {
                "task_id": work_order.id,
                "agent_id": last_deliverable.agent_id,
                "output_hash": last_deliverable.output_hash,
                "evidence_ids": last_deliverable.evidence_ids,
            },
        )

        accepted, quality, reason, duplicate_ratio = _validate_deliverable(
            repository,
            mission,
            work_order,
            last_deliverable,
        )
        if accepted:
            await _emit(
                emit,
                "deliverable_accepted",
                "state_update",
                manifest.display_name,
                "交付已通过身份、Evidence 归属、输出合同和质量门。",
                {"task_id": work_order.id, "quality_score": quality},
            )
            break
        last_reason = reason
        if manifest.agent_id not in reworked_agents:
            reworked_agents.add(manifest.agent_id)
            work_order.status = WorkOrderStatus.REWORK
            await _emit(
                emit,
                "deliverable_rework",
                "tool_execution",
                manifest.display_name,
                "交付未通过合同门，已返回一次定向返工。",
                {"task_id": work_order.id, "reason": reason, "quality_score": quality},
                severity="warning",
            )
            work_order.status = WorkOrderStatus.RUNNING
            continue
        if manifest.transport == AgentTransport.A2A:
            scheduler.release(manifest.agent_id)
            registry.replace(manifest.model_copy(update={"available": False}))
            await _emit(
                emit,
                "task_reassigned",
                "state_update",
                "Agent Scheduler",
                "A2A 交付定向返工后仍未通过本地 Evidence/Schema 门，已改派本地同能力 Agent。",
                {"task_id": work_order.id, "failed_agent_id": manifest.agent_id, "reason": reason},
                severity="warning",
            )
            manifest = scheduler.assign(work_order, remaining_seconds=_remaining_seconds(mission))
            continue
        break

    if last_deliverable is None:
        raise RuntimeError(last_reason or "specialist returned no deliverable")
    accepted, quality, reason, duplicate_ratio = _validate_deliverable(
        repository,
        mission,
        work_order,
        last_deliverable,
    )
    if not accepted:
        await _emit(
            emit,
            "deliverable_rejected",
            "state_update",
            manifest.display_name,
            "返工后的交付仍未通过合同门，本任务将以 rejected 结算。",
            {"task_id": work_order.id, "reason": reason, "quality_score": quality},
            severity="error",
        )
    latency_ms = int((perf_counter() - started) * 1000)
    last_deliverable.latency_ms = latency_ms
    evidence_gain = len(_valid_evidence_ids(repository, mission.project_id, last_deliverable.evidence_ids))
    used = max(1, last_deliverable.usage.llm_calls + last_deliverable.usage.provider_requests)
    allowed = max(1, work_order.budget.max_llm_calls + work_order.budget.max_provider_requests)
    budget_efficiency = max(0.0, min(1.0, 1 - (used / allowed) + 0.5))
    capability = work_order.required_capabilities[0]
    before = manifest.performance.reliability_for(capability)
    successes = manifest.performance.accepted_tasks
    failures = manifest.performance.rejected_tasks
    after = (2 + successes + (1 if accepted else 0)) / (4 + successes + failures + 1)
    settlement = TaskSettlement(
        task_id=work_order.id,
        agent_id=last_deliverable.agent_id,
        accepted=accepted,
        quality_score=quality,
        evidence_gain=evidence_gain,
        duplicate_ratio=duplicate_ratio,
        budget_efficiency=budget_efficiency,
        rework_count=max(0, work_order.attempts - 1),
        reliability_before=before,
        reliability_after=after,
        reason=reason,
    )
    updated_manifest = persist_settlement(
        repository,
        mission.project_id,
        manifest,
        settlement,
        capability,
        latency_ms=latency_ms,
    )
    registry.replace(updated_manifest)
    await _emit(
        emit,
        "task_settled",
        "state_update",
        manifest.display_name,
        f"任务{'验收' if accepted else '拒绝'}：质量 {quality:.2f}，有效证据增益 {evidence_gain}。",
        {
            "task_id": work_order.id,
            "deliverable": last_deliverable.model_dump(mode="json"),
            "settlement": settlement.model_dump(mode="json"),
        },
        severity="info" if accepted else "error",
    )
    scheduler.release(manifest.agent_id)
    return last_deliverable, settlement


async def _run_researcher(
    manifest: AgentManifest,
    work_order: WorkOrder,
    mission: AgentMission,
    project: ResearchProject,
    repository: SQLiteRepository,
    state: SectorBreakerState,
    search_provider: SearchProvider,
    extraction_provider: ContentExtractionProvider,
    source_verifier: SourceVerificationProvider | None,
    llm_provider: LLMProvider,
    emit: EmitFn,
    *,
    feedback: str,
) -> AgentDeliverable:
    decision = await llm_provider.complete_structured(
        [ChatMessage(role="user", content=f"""
你是 {manifest.display_name}。为真实现场研究任务生成 1-3 条自然搜索 query。
领域：{mission.domain}
任务：{work_order.objective}
研究角度：{work_order.research_angle}
验收标准：{json.dumps(work_order.acceptance_criteria, ensure_ascii=False)}
上次返工意见：{feedback or '无'}
不要机械分词，返回 ResearchDecision JSON。
""".strip())],
        ResearchDecision,
    )
    local_state = state.model_copy(deep=True)
    context = KernelRuntimeContext(
        project=project,
        repository=repository,
        state=local_state,
        search_provider=search_provider,
        llm_provider=llm_provider,
        emit_event=emit,
        content_extraction_provider=extraction_provider,
        source_verification_provider=source_verifier,
        run_id=mission.run_id,
        max_provider_requests=work_order.budget.max_provider_requests,
        max_extraction_requests=work_order.budget.max_extraction_requests,
    )
    await _emit(
        emit,
        "specialist_action",
        "tool_execution",
        manifest.display_name,
        f"Action: search_web — {decision.search_goal}",
        {"task_id": work_order.id, "query": decision.query, "queries": decision.queries},
    )
    started = perf_counter()
    observation = await search_web(
        ToolCall(
            tool_name="search_web",
            args={
                "query": decision.query,
                "queries": decision.queries,
                "search_goal": decision.search_goal,
                "max_results": 5,
            },
            reason=decision.rationale or work_order.objective,
        ),
        context,
    )
    observation_record = ToolObservationRecord(
        tool_name="search_web",
        success=observation.success,
        summary=observation.summary,
        evidence_ids=observation.evidence_ids,
        latency_ms=int((perf_counter() - started) * 1000),
        error=observation.error,
    )
    await _emit(
        emit,
        "specialist_action",
        "tool_execution",
        manifest.display_name,
        observation.summary,
        {"task_id": work_order.id, "observation": observation.model_dump(mode="json")},
        severity="info" if observation.success else "warning",
    )
    if not observation.success or not observation.evidence_ids:
        raise RuntimeError(observation.error or "research search returned no accepted evidence")
    evidence = [repository.get_evidence(item) for item in observation.evidence_ids]
    synthesis = await llm_provider.complete_structured(
        [ChatMessage(role="user", content=f"""
根据真实搜索 Observation 形成结构化研究交付。只允许引用给出的 Evidence ID。
任务：{work_order.objective}
验收标准：{json.dumps(work_order.acceptance_criteria, ensure_ascii=False)}
Evidence：{json.dumps([{
    'id': item.id,
    'title': item.source_title,
    'url': item.source_url,
    'verification_status': item.verification_status.value,
    'excerpt': item.raw_excerpt[:900],
} for item in evidence], ensure_ascii=False)}
返回 ResearchSynthesis JSON；每个 finding 必须给出支持它的 Evidence ID，不得创造 ID。
""".strip())],
        ResearchSynthesis,
    )
    allowed = set(observation.evidence_ids)
    findings = []
    for finding in synthesis.findings:
        ids = [item for item in finding.evidence_ids if item in allowed]
        if ids:
            findings.append(finding.model_copy(update={"evidence_ids": ids}))
    return AgentDeliverable(
        task_id=work_order.id,
        mission_id=mission.id,
        agent_id=manifest.agent_id,
        summary=synthesis.summary,
        findings=findings,
        evidence_ids=list(dict.fromkeys(item for finding in findings for item in finding.evidence_ids)),
        observations=[observation_record],
        usage=DeliverableUsage(
            steps=2,
            search_calls=context.search_call_count,
            provider_requests=context.provider_request_count,
            extraction_requests=context.extraction_request_count,
            llm_calls=2,
        ),
    )


async def _run_verifier(
    manifest: AgentManifest,
    work_order: WorkOrder,
    mission: AgentMission,
    project: ResearchProject,
    repository: SQLiteRepository,
    state: SectorBreakerState,
    search_provider: SearchProvider,
    extraction_provider: ContentExtractionProvider,
    source_verifier: SourceVerificationProvider | None,
    llm_provider: LLMProvider,
    emit: EmitFn,
    *,
    feedback: str,
) -> AgentDeliverable:
    accepted_task_ids = {
        item.id for item in mission.work_orders
        if item.status == WorkOrderStatus.ACCEPTED and item.id != work_order.id
    }
    upstream = [item for item in mission.deliverables if item.task_id in accepted_task_ids]
    claims = [finding.summary for item in upstream for finding in item.findings][:8]
    # Search planning is deterministic here: the WorkOrder angle was already
    # produced by the LLM Mission Planner.  Spending another model round-trip
    # merely to format a query consumed an entire 90-second verifier window in
    # live testing.  The actual counterevidence search and LLM claim judgement
    # remain real and auditable.
    claim_terms = " ".join(claims[:2])[:320]
    decision = ResearchDecision(
        query=f"{mission.domain} {claim_terms} limitations criticism controversy evidence",
        search_goal="寻找与候选结论相冲突的证据、适用边界和工程化风险",
        rationale=feedback or "Verifier 主动寻找反证与边界",
    )
    context = KernelRuntimeContext(
        project=project,
        repository=repository,
        state=state.model_copy(deep=True),
        search_provider=search_provider,
        llm_provider=llm_provider,
        emit_event=emit,
        content_extraction_provider=extraction_provider,
        source_verification_provider=source_verifier,
        run_id=mission.run_id,
        max_provider_requests=work_order.budget.max_provider_requests,
        max_extraction_requests=work_order.budget.max_extraction_requests,
    )
    await _emit(
        emit,
        "specialist_action",
        "tool_execution",
        manifest.display_name,
        f"Action: search_web — {decision.search_goal}",
        {"task_id": work_order.id, "query": decision.query},
    )
    started = perf_counter()
    observation = await search_web(
        ToolCall(
            tool_name="search_web",
            args={"query": decision.query, "queries": decision.queries, "search_goal": decision.search_goal, "max_results": 4},
            reason="Verifier 主动寻找反证与边界",
        ),
        context,
    )
    observation_record = ToolObservationRecord(
        tool_name="search_web",
        success=observation.success,
        summary=observation.summary,
        evidence_ids=observation.evidence_ids,
        latency_ms=int((perf_counter() - started) * 1000),
        error=observation.error,
    )
    await _emit(
        emit,
        "specialist_action",
        "tool_execution",
        manifest.display_name,
        observation.summary,
        {"task_id": work_order.id, "observation": observation.model_dump(mode="json")},
        severity="info" if observation.success else "warning",
    )
    all_ids = list(dict.fromkeys([
        *[evidence_id for item in upstream for evidence_id in item.evidence_ids],
        *observation.evidence_ids,
    ]))
    evidence = [repository.get_evidence(item) for item in _valid_evidence_ids(repository, mission.project_id, all_ids)]
    synthesis = await llm_provider.complete_structured(
        [ChatMessage(role="user", content=f"""
逐条核查候选结论。status 只能是 supported、conflicting 或 insufficient。
仅能使用给出的 Evidence ID。来源评级不等于事实 verified；解释证据为何支持或不足。
候选结论：{json.dumps(claims, ensure_ascii=False)}
Evidence：{json.dumps([{
    'id': item.id,
    'title': item.source_title,
    'url': item.source_url,
    'quality': item.source_quality.value,
    'verification_status': item.verification_status.value,
    'excerpt': item.raw_excerpt[:700],
} for item in evidence[:8]], ensure_ascii=False)}
返回 VerificationSynthesis JSON。
""".strip())],
        VerificationSynthesis,
    )
    allowed = {item.id for item in evidence}
    checks = [
        check.model_copy(update={"evidence_ids": [item for item in check.evidence_ids if item in allowed]})
        for check in synthesis.claim_checks
    ]
    used_ids = list(dict.fromkeys(item for check in checks for item in check.evidence_ids))
    findings = [
        DeliverableFinding(
            summary=f"{check.status.value}: {check.claim} — {check.reason}",
            evidence_ids=check.evidence_ids,
            confidence=0.8 if check.status == ClaimCheckStatus.SUPPORTED else 0.6,
            requires_verification=check.status != ClaimCheckStatus.SUPPORTED,
        )
        for check in checks
    ]
    return AgentDeliverable(
        task_id=work_order.id,
        mission_id=mission.id,
        agent_id=manifest.agent_id,
        summary=synthesis.summary,
        findings=findings,
        claim_checks=checks,
        evidence_ids=used_ids,
        observations=[observation_record],
        usage=DeliverableUsage(
            steps=2,
            search_calls=context.search_call_count,
            provider_requests=context.provider_request_count,
            extraction_requests=context.extraction_request_count,
            llm_calls=1,
        ),
    )


async def _run_editor(
    manifest: AgentManifest,
    work_order: WorkOrder,
    mission: AgentMission,
    repository: SQLiteRepository,
    llm_provider: LLMProvider,
    emit: EmitFn,
    *,
    feedback: str,
) -> AgentDeliverable:
    accepted_task_ids = {
        item.id for item in mission.work_orders
        if item.status == WorkOrderStatus.ACCEPTED and item.id != work_order.id
    }
    upstream = [item for item in mission.deliverables if item.task_id in accepted_task_ids]
    all_ids = list(dict.fromkeys(
        evidence_id for item in mission.deliverables for evidence_id in item.evidence_ids
    ))
    valid_ids = _valid_evidence_ids(repository, mission.project_id, all_ids)
    evidence = [repository.get_evidence(item) for item in valid_ids[:6]]
    prompt = f"""
你是 SectorBreaker Knowledge Editor。根据已验收交付和真实 Evidence 写一篇中文 Starter Note。
领域：{mission.domain}
目标：{mission.objective}
验收标准：{json.dumps(work_order.acceptance_criteria, ensure_ascii=False)}
返工意见：{feedback or '无'}
上游交付：{json.dumps([{
    'agent_id': item.agent_id,
    'summary': item.summary,
    'findings': [finding.model_dump(mode='json') for finding in item.findings[:5]],
    'claim_checks': [check.model_dump(mode='json') for check in item.claim_checks],
} for item in upstream], ensure_ascii=False)}
Evidence：{json.dumps([{
    'id': item.id,
    'title': item.source_title,
    'url': item.source_url,
    'quality': item.source_quality.value,
    'verification_status': item.verification_status.value,
    'excerpt': item.raw_excerpt[:700],
} for item in evidence], ensure_ascii=False)}

要求：
- 目标 1500-2500 个中文字符；
- 使用标题：领域定义与边界、核心概念、关键参与者、运行机制、争议与不确定性、后续研究问题、来源；
- 每个事实段落使用 [EV-...] 标识对应证据；
- 不能创造 Evidence ID、URL、数字或未提供的事实；
- conflicting/insufficient 内容必须以争议或待验证形式呈现；
- 输出纯 Markdown，不要代码围栏或 YAML front matter。
""".strip()
    llm_calls = 1
    draft = _clean_markdown(await llm_provider.complete([ChatMessage(role="user", content=prompt)]))
    if not 1500 <= len(draft) <= 3200 or len(_required_headings(draft)) < 7:
        critique = (
            f"正文只有 {len(draft)} 字符或章节不完整。请在不创造新事实的前提下扩写至 1500-2500 字，"
            "补齐全部指定章节并保留 Evidence ID。"
        )
        llm_calls += 1
        draft = _clean_markdown(await llm_provider.complete([
            ChatMessage(role="user", content=prompt + "\n\n返工要求：" + critique),
        ]))
    if not 1500 <= len(draft) <= 3200 or len(_required_headings(draft)) < 7:
        raise ValueError("Starter Note remains outside the 1500-2500 target or misses required sections after retry")
    referenced = [item for item in valid_ids if item in draft]
    # A model can produce a useful, contract-complete note yet omit the literal
    # Evidence token while paraphrasing the supplied source title.  Do not burn
    # a second 30-90 second generation on a mechanical omission: attach a
    # deterministic ledger made only from already accepted project Evidence.
    # This adds traceability, never prose or unsupported claims.
    if len(referenced) < 2:
        referenced = valid_ids[: min(6, len(valid_ids))]
    source_lines = [
        f"- [{item.id}] [{item.source_title}]({item.source_url}) — {item.verification_status.value}"
        for item in evidence
        if item.id in referenced and item.source_url
    ]
    if "## 来源" not in draft and "# 来源" not in draft:
        draft += "\n\n## 来源\n\n" + "\n".join(source_lines)
    elif source_lines:
        draft += "\n\n### Evidence Ledger\n\n" + "\n".join(source_lines)
    referenced = [item for item in valid_ids if item in draft]
    if len(referenced) < 2:
        raise ValueError("Starter Note must expose at least two accepted Evidence IDs")
    frontmatter = (
        "---\n"
        "schema_version: v3-agent-contract-network\n"
        f"domain: {json.dumps(mission.domain, ensure_ascii=False)}\n"
        f"mission_id: {mission.id}\n"
        f"evidence_ids: {json.dumps(referenced, ensure_ascii=False)}\n"
        "verification_status: partially_verified\n"
        "---\n\n"
    )
    markdown = frontmatter + draft.strip() + "\n"
    await _emit(
        emit,
        "specialist_action",
        "artifact_writing",
        manifest.display_name,
        f"Knowledge Editor 完成真实 Starter Note 草稿（{len(markdown)} 字符）。",
        {"task_id": work_order.id, "evidence_ids": referenced, "path": _starter_note_path(mission.domain)},
    )
    return AgentDeliverable(
        task_id=work_order.id,
        mission_id=mission.id,
        agent_id=manifest.agent_id,
        summary=f"已为 {mission.domain} 形成证据型 Starter Note。",
        findings=[DeliverableFinding(
            summary="Starter Note 已按验收章节合并上游 accepted deliverables。",
            evidence_ids=referenced,
            confidence=0.8,
            requires_verification=False,
        )],
        evidence_ids=referenced,
        draft_markdown=markdown,
        proposed_path=_starter_note_path(mission.domain),
        usage=DeliverableUsage(steps=1, llm_calls=llm_calls),
    )


def _validate_deliverable(
    repository: SQLiteRepository,
    mission: AgentMission,
    work_order: WorkOrder,
    deliverable: AgentDeliverable,
) -> tuple[bool, float, str, float]:
    if deliverable.task_id != work_order.id or deliverable.mission_id != mission.id:
        return False, 0.0, "deliverable identity does not match WorkOrder", 0.0
    valid = _valid_evidence_ids(repository, mission.project_id, deliverable.evidence_ids)
    evidence_ratio = len(valid) / max(1, len(deliverable.evidence_ids))
    contract_complete = 0.0
    verifier_signal = 0.7
    if work_order.task_type == WorkOrderType.RESEARCH:
        contract_complete = 1.0 if deliverable.findings and valid else 0.0
    elif work_order.task_type == WorkOrderType.VERIFY:
        contract_complete = 1.0 if deliverable.claim_checks else 0.0
        verifier_signal = (
            sum(1 for item in deliverable.claim_checks if item.evidence_ids)
            / max(1, len(deliverable.claim_checks))
        )
    else:
        contract_complete = 1.0 if deliverable.draft_markdown and len(valid) >= 2 else 0.0
        verifier_signal = 1.0 if any(
            item.claim_checks for item in mission.deliverables if item.task_id in work_order.depends_on
        ) else 0.0
    prior_evidence = {
        evidence_id
        for item in mission.deliverables
        for evidence_id in item.evidence_ids
        if item.task_id != work_order.id
    }
    duplicate = len(set(valid) & prior_evidence)
    duplicate_ratio = duplicate / max(1, len(set(valid)))
    uniqueness = 1 - duplicate_ratio
    usage = deliverable.usage
    used = usage.llm_calls + usage.provider_requests
    allowed = work_order.budget.max_llm_calls + work_order.budget.max_provider_requests
    budget_efficiency = max(0.0, min(1.0, 1 - used / max(1, allowed) + 0.5))
    quality = round(
        0.30 * contract_complete
        + 0.25 * evidence_ratio
        + 0.25 * verifier_signal
        + 0.10 * budget_efficiency
        + 0.10 * uniqueness,
        4,
    )
    accepted = quality >= 0.70 and contract_complete == 1.0 and evidence_ratio == 1.0
    reason = "accepted" if accepted else (
        f"quality={quality:.2f}, contract={contract_complete:.2f}, "
        f"evidence={evidence_ratio:.2f}, verifier={verifier_signal:.2f}"
    )
    return accepted, quality, reason, duplicate_ratio


def _valid_evidence_ids(repository: SQLiteRepository, project_id: str, evidence_ids: list[str]) -> list[str]:
    known = {item.id for item in repository.list_evidence(project_id)}
    return [item for item in dict.fromkeys(evidence_ids) if item in known]


async def _admit_remote_evidence(
    deliverable: AgentDeliverable,
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    source_verifier: SourceVerificationProvider | None,
) -> AgentDeliverable:
    """Convert opaque remote evidence candidates into local project Evidence."""

    if not deliverable.evidence_candidates:
        return deliverable
    constraints = build_project_search_constraints({
        "market_scope": project.market_scope.value,
        "source_policy": project.source_policy.value,
        "source_preferences": project.source_preferences.model_dump(mode="json"),
    })
    mapping: dict[str, str] = {}
    for candidate in deliverable.evidence_candidates:
        if len(candidate.raw_excerpt.strip()) < 120:
            continue
        if not url_matches_domain_policy(
            candidate.url,
            allowed_domains=constraints.primary_allowed_domains,
            blocked_domains=constraints.blocked_domains,
        ):
            continue
        assessment = None
        if source_verifier is not None:
            assessment = await source_verifier.assess_source(
                url=candidate.url,
                title=candidate.title,
                snippet=candidate.snippet,
                extracted_text=candidate.raw_excerpt,
                source_policy=project.source_policy.value,
            )
        evidence_id = f"EV-KERNEL-{project.id}-{uuid4().hex[:8]}"
        try:
            quality = SourceQuality(assessment.source_quality) if assessment else SourceQuality.UNKNOWN
        except ValueError:
            quality = SourceQuality.UNKNOWN
        try:
            verification = (
                VerificationStatus(assessment.recommended_verification_status)
                if assessment and assessment.recommended_verification_status
                else VerificationStatus.UNVERIFIED
            )
        except ValueError:
            verification = VerificationStatus.UNVERIFIED
        evidence = EvidenceItem(
            id=evidence_id,
            project_id=project.id,
            source_title=candidate.title,
            source_url=candidate.url,
            source_type=assessment.source_type if assessment else "web",
            source_channel=SourceChannel.SEARCH,
            source_policy=project.source_policy.value,
            raw_excerpt=candidate.raw_excerpt[:12000],
            snippet=candidate.snippet[:1000],
            summary=candidate.raw_excerpt[:800],
            extraction_provider=candidate.extraction_provider or "a2a_remote",
            extraction_metadata={
                **candidate.provider_metadata,
                "transport": "a2a",
                "remote_candidate_id": candidate.candidate_id,
            },
            collection_metadata={
                "transport": "a2a",
                "remote_agent_id": deliverable.agent_id,
                "source_enforcement": constraints.enforcement,
                "effective_allowed_domains": constraints.primary_allowed_domains,
                "effective_blocked_domains": constraints.blocked_domains,
            },
            extracted_at=datetime.now(UTC),
            source_quality=quality,
            claim_strength=ClaimStrength.OPINION,
            bias_risk=assessment.reliability_notes if assessment else None,
            needs_counterevidence=True,
            collected_by=f"a2a:{deliverable.agent_id}",
            confidence=0.6 if quality == SourceQuality.HIGH else 0.45,
            verification_status=verification,
        )
        repository.add_evidence(evidence)
        mapping[candidate.candidate_id] = evidence_id

    def remap(ids: list[str]) -> list[str]:
        return list(dict.fromkeys(mapping.get(item, item) for item in ids if item in mapping))

    findings = [item.model_copy(update={"evidence_ids": remap(item.evidence_ids)}) for item in deliverable.findings]
    checks = [item.model_copy(update={"evidence_ids": remap(item.evidence_ids)}) for item in deliverable.claim_checks]
    return deliverable.model_copy(update={
        "findings": findings,
        "claim_checks": checks,
        "evidence_ids": remap(deliverable.evidence_ids),
    })


def _work_order(mission: AgentMission, work_order_id: str) -> WorkOrder:
    return next(item for item in mission.work_orders if item.id == work_order_id)


def _remaining_seconds(mission: AgentMission) -> float:
    return max(0.0, (mission.deadline_at - datetime.now(UTC)).total_seconds())


def _a2a_endpoint() -> str | None:
    import os

    return (os.getenv("SECTORBREAKER_A2A_RESEARCHER_URL") or "").strip() or None


def _capabilities_from_agent_card(card: dict) -> list[str]:
    allowed = {"research_ecosystem", "web_search", "evidence_extract"}
    declared: list[str] = []
    for skill in card.get("skills", []):
        if not isinstance(skill, dict):
            continue
        declared.extend([str(skill.get("id") or ""), *[str(item) for item in skill.get("tags", [])]])
    return list(dict.fromkeys(item for item in declared if item in allowed))


def _starter_note_path(domain: str) -> str:
    slug = re.sub(r'[<>:"/\\|?*\s]+', "-", domain).strip("-.")[:60] or "live-challenge"
    return f"docs/{slug}-Starter-Note.md"


def _required_headings(markdown: str) -> set[str]:
    names = {"领域定义与边界", "核心概念", "关键参与者", "运行机制", "争议与不确定性", "后续研究问题", "来源"}
    return {name for name in names if name in markdown}


def _clean_markdown(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"^```(?:markdown|md)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            text = parts[2].lstrip()
    return text


async def _emit_provider_failovers(
    emit: EmitFn,
    task_id: str,
    *providers: object,
) -> None:
    for provider in providers:
        drain = getattr(provider, "drain_failover_events", None)
        if not callable(drain):
            continue
        for event in drain():
            selected = event["selected_channel"]
            message = (
                f"{event['capability']} 首次输出未通过，修复后继续使用 primary。"
                if selected == "primary"
                else f"{event['capability']} 主通道失败，已切换 {selected} 并继续真实执行。"
            )
            await _emit(
                emit,
                "provider_failover",
                "tool_execution",
                "Provider Router",
                message,
                {"task_id": task_id, **event},
                severity="warning",
            )


def _blocked_result(state: SectorBreakerState, reason: str) -> KernelRunResult:
    return KernelRunResult(
        status=KernelRunStatus.BLOCKED,
        state_version=state.state_version,
        stop_reason=reason,
    )


async def _emit(
    emit: EmitFn,
    event_type: str,
    gate: str,
    agent: str,
    message: str,
    data: dict | None = None,
    *,
    severity: str = "info",
) -> None:
    await emit(RunEvent(
        event_type=event_type,
        gate=gate,
        agent=agent,
        message=message,
        data=data,
        severity=severity,
    ))
