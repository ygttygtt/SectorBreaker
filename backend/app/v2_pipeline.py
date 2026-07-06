"""V2 stateful ReAct-style knowledge pipeline.

This path wires the V2 state/memory foundation into the real project run while
reusing the proven V1 artifact writer for stable Markdown output.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from backend.app.agent_state import (
    AgentAction,
    AgentDecision,
    ContextPackBuilder,
    KnowledgeClaim,
    KnowledgeLayerId,
    ReportInternalizer,
    SectorBreakerState,
    SourceMemory,
    SourceUse,
    TaskMemory,
    ToolAttempt,
)
from backend.app.agent_state.models import CoverageStatus, TrustLevel
from backend.app.agents.iceberg_agent import IcebergRiskAgent
from backend.app.agents.specialists import SpecialistTaskPlanner, default_specialist_specs
from backend.app.providers.interfaces import LLMProvider, SearchProvider, SearchQuery
from backend.app.schemas import Artifact, EvidenceItem, ResearchProject, RunEvent, SourcePolicy
from backend.app.storage.sqlite import SQLiteRepository
from backend.app.v1_pipeline import (
    _V1_ZERO_EVIDENCE_BLOCK_MESSAGE,
    _build_artifacts,
    _build_knowledge_database,
    _filter_v1_search_results,
    _persist_search_results,
)


_LAYER_QUERY_HINTS: dict[KnowledgeLayerId, list[str]] = {
    KnowledgeLayerId.PREREQUISITE: ["前置知识", "小白入门", "基础概念"],
    KnowledgeLayerId.WHAT_WHY: ["是什么", "为什么存在", "需求 痛点"],
    KnowledgeLayerId.WHO: ["谁在用", "主要玩家", "头部机构 用户"],
    KnowledgeLayerId.HOW: ["原理", "怎么实现", "工具 框架 流程"],
    KnowledgeLayerId.MONEY: ["怎么赚钱", "商业模式", "成本 价格 产业链"],
    KnowledgeLayerId.RISKS: ["风险", "政策 监管", "骗局 防坑 稳定性"],
}


async def run_v2_react_knowledge_pipeline(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    emit: Callable[[RunEvent], Awaitable[None]] | None = None,
) -> list[Artifact]:
    """Run the V2 stateful research path and persist V1-compatible artifacts."""

    async def emit_event(event: RunEvent) -> None:
        if emit is not None:
            await emit(event)

    state = SectorBreakerState.initialize(
        project_id=project.id,
        domain=project.domain,
        user_goal=f"为“{project.domain}”构建可持续扩展的 Obsidian 领域知识库",
        market_scope=project.market_scope.value,
        source_policy=project.source_policy.value,
    )
    evidence = list(repository.list_evidence(project.id))

    await emit_event(RunEvent(
        event_type="node_started",
        gate="master_agent",
        agent="V2 Master Agent",
        message="V2 Master Agent 初始化状态、知识 Schema 和运行记忆",
        data={"schema": state.knowledge_schema.model_dump(mode="json")},
    ))

    await _internalize_uploaded_documents(
        project=project,
        repository=repository,
        state=state,
        emit_event=emit_event,
    )

    if project.source_policy != SourcePolicy.USER_MATERIALS_ONLY and search_provider is not None:
        await _run_layer_research(
            project=project,
            repository=repository,
            search_provider=search_provider,
            state=state,
            evidence=evidence,
            emit_event=emit_event,
        )
    else:
        await emit_event(RunEvent(
            event_type="node_degraded",
            gate="source_collection",
            agent="V2 Master Agent",
            message="当前配置不主动搜索，V2 将仅基于上传材料和已有证据建库",
            severity="warning",
        ))

    if not evidence and not state.shared_knowledge.source_memories:
        await emit_event(RunEvent(
            event_type="node_blocked",
            gate="coverage_evaluation",
            agent="V2 Master Agent",
            message=_V1_ZERO_EVIDENCE_BLOCK_MESSAGE,
            severity="error",
            data={"state": state.model_dump(mode="json")},
        ))
        raise RuntimeError(_V1_ZERO_EVIDENCE_BLOCK_MESSAGE)

    await emit_event(RunEvent(
        event_type="node_completed",
        gate="coverage_evaluation",
        agent="V2 Master Agent",
        message="V2 分层覆盖判断完成，开始生成知识库文档",
        data={
            "decisions": [item.model_dump(mode="json") for item in state.decision_log[-8:]],
            "source_memory_count": len(state.shared_knowledge.source_memories),
            "claim_count": len(state.shared_knowledge.claims),
        },
    ))

    database = await _build_knowledge_database(
        project=project,
        evidence=evidence,
        llm_provider=llm_provider,
        emit_event=emit_event,
    )
    artifacts = await _build_artifacts(
        project,
        database,
        [item.id for item in evidence],
        llm_provider=llm_provider,
        emit_event=emit_event,
    )
    for artifact in artifacts:
        repository.add_artifact(artifact)

    await emit_event(RunEvent(
        event_type="node_completed",
        gate="obsidian_export",
        agent="V2 Export Writer",
        message="V2 状态调研完成，Markdown 产物已写入项目",
        data={"state_version": state.state_version},
    ))
    return artifacts


async def _internalize_uploaded_documents(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    state: SectorBreakerState,
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> None:
    list_documents = getattr(repository, "list_documents", None)
    if list_documents is None:
        return
    documents = list_documents(project.id)
    if not documents:
        return
    internalizer = ReportInternalizer()
    await emit_event(RunEvent(
        event_type="node_started",
        gate="external_report_intake",
        agent="V2 Report Internalizer",
        message=f"V2 正在内化上传材料：{len(documents)} 个文档",
    ))
    for document in documents:
        report = internalizer.internalize(document, domain=project.domain)
        internalizer.apply_to_state(state, report)
        await emit_event(RunEvent(
            event_type="evidence_collected",
            gate="external_report_intake",
            agent="V2 Report Internalizer",
            message=(
                f"已内化上传材料：{getattr(document, 'file_name', None) or document.id}，"
                f"claims={len(report.claims)}，entities={len(report.entities)}，questions={len(report.open_questions)}"
            ),
            data=report.model_dump(mode="json"),
        ))
    state.add_decision(AgentDecision(
        action=AgentAction.CONTINUE,
        reason="上传材料已进入 V2 shared knowledge，后续搜索将作为补充和验证。",
    ))


async def _run_layer_research(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    search_provider: SearchProvider,
    state: SectorBreakerState,
    evidence: list[EvidenceItem],
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> None:
    specs = {spec.layer_id: spec for spec in default_specialist_specs()}
    context_builder = ContextPackBuilder()
    follow_up_planner = SpecialistTaskPlanner()
    iceberg_agent = IcebergRiskAgent()

    for layer in state.knowledge_schema.layers:
        state.current_layer_id = layer.id
        task = TaskMemory(
            layer_id=layer.id,
            objective=layer.goal,
            checklist=layer.completion_criteria,
        )
        state.add_task_memory(task)
        spec = specs.get(layer.id)
        await emit_event(RunEvent(
            event_type="node_started",
            gate="specialist_react_loop",
            agent=spec.name if spec else "V2 Specialist Agent",
            message=f"开始 V2 分层 ReAct：{layer.title}",
            data={"layer": layer.model_dump(mode="json")},
        ))

        pack = context_builder.build(state, layer_id=layer.id, task_memory=task, active_task=layer.goal)
        query = _query_for_layer(project.domain, layer.id, pack.coverage_gaps)
        results = await search_provider.search(SearchQuery(
            query=query,
            market_scope=project.market_scope.value,
            max_results=6,
            blocked_domains=[],
            allowed_domains=None,
        ))
        accepted = _filter_v1_search_results(results, project=project)
        if not accepted and results:
            accepted = results[:2]
            await emit_event(RunEvent(
                event_type="node_degraded",
                gate="source_collection",
                agent="V2 Specialist Agent",
                message="严格过滤未采纳结果，V2 已保留原始搜索结果作为待验证线索",
                severity="warning",
                data={"query": query, "raw_result_count": len(results)},
            ))
        added_ids = await _persist_search_results(
            project=project,
            repository=repository,
            evidence=evidence,
            results=accepted,
            emit_event=emit_event,
        )
        observation = "；".join(result.title for result in accepted[:4]) or "本层搜索没有采纳到可用结果。"
        task.attempts.append(ToolAttempt(
            tool="search",
            action="query",
            query_or_input=query,
            observation=observation,
            success=True,
            useful=bool(added_ids),
            evidence_ids=added_ids,
        ))
        _add_search_memory_to_state(
            state=state,
            layer_id=layer.id,
            accepted_titles=[result.title for result in accepted],
            evidence_ids=added_ids,
            query=query,
        )
        if layer.id == KnowledgeLayerId.RISKS:
            findings = iceberg_agent.extract_risk_terms(observation, domain=project.domain)
            source_memories, claims, questions = iceberg_agent.findings_to_state_objects(
                domain=project.domain,
                findings=findings,
            )
            state.shared_knowledge.source_memories.extend(source_memories)
            state.shared_knowledge.claims.extend(claims)
            state.shared_knowledge.open_questions.extend(questions)

        follow_ups = follow_up_planner.discover_follow_up_tasks(
            domain=project.domain,
            layer_id=layer.id,
            observations=[observation],
        )
        for follow_up in follow_ups[:3]:
            state.shared_knowledge.open_questions.append(
                _follow_up_to_open_question(follow_up.title, follow_up.reason, layer.id)
            )

        _judge_layer_coverage(state, layer.id, added_ids)
        coverage_event: dict[str, Any] = {
            "event_type": "node_completed" if added_ids else "node_degraded",
            "gate": "coverage_evaluation",
            "agent": "V2 Master Agent",
            "message": f"{layer.title} 覆盖判断：{layer.coverage_status.value}",
            "data": {
                "query": query,
                "accepted_evidence_ids": added_ids,
                "context_pack": pack.model_dump(mode="json"),
                "follow_up_count": len(follow_ups),
            },
        }
        if not added_ids:
            coverage_event["severity"] = "warning"
        await emit_event(RunEvent(**coverage_event))


def _query_for_layer(domain: str, layer_id: KnowledgeLayerId, gaps: list[str]) -> str:
    hints = " ".join(_LAYER_QUERY_HINTS.get(layer_id, []))
    gap_hint = " ".join(gaps[:2])
    return f"{domain} {hints} {gap_hint} 2026".strip()


def _add_search_memory_to_state(
    *,
    state: SectorBreakerState,
    layer_id: KnowledgeLayerId,
    accepted_titles: list[str],
    evidence_ids: list[str],
    query: str,
) -> None:
    if not accepted_titles and not evidence_ids:
        return
    memory = SourceMemory(
        source_id=f"search:{query}",
        source_kind="search",
        title=f"{layer_id.value} 搜索结果",
        summary="；".join(accepted_titles[:6]) or query,
        use=SourceUse.EVIDENCE if evidence_ids else SourceUse.SEARCH_LEAD,
        trust_level=TrustLevel.UNKNOWN,
        evidence_ids=evidence_ids,
        related_layer_ids=[layer_id],
        keep_reason="V2 specialist ReAct 搜索采纳结果，进入 shared knowledge 供后续写作和覆盖判断使用。",
    )
    state.shared_knowledge.source_memories.append(memory)
    if accepted_titles:
        state.shared_knowledge.claims.append(KnowledgeClaim(
            text=f"{layer_id.value} 搜索观察：{'；'.join(accepted_titles[:4])}",
            layer_ids=[layer_id],
            evidence_ids=evidence_ids,
            source_memory_ids=[memory.id],
            confidence=0.45,
            trust_level=TrustLevel.UNKNOWN,
            verification_status="partially_verified" if evidence_ids else "unverified",
            needs_verification=True,
            notes="V2 分层搜索观察，后续应结合更多来源验证。",
        ))


def _follow_up_to_open_question(title: str, reason: str, layer_id: KnowledgeLayerId):
    from backend.app.agent_state.models import OpenQuestion

    return OpenQuestion(
        question=title,
        layer_ids=[layer_id],
        reason=reason,
        suggested_actions=["继续搜索", "查找原始来源", "加入下一轮 specialist ReAct"],
    )


def _judge_layer_coverage(state: SectorBreakerState, layer_id: KnowledgeLayerId, added_ids: list[str]) -> None:
    layer = state.knowledge_schema.layer(layer_id)
    if layer is None:
        return
    if len(added_ids) >= 2:
        layer.coverage_status = CoverageStatus.SUFFICIENT
        action = AgentAction.CONTINUE
        reason = f"{layer.title} 已采纳 {len(added_ids)} 条证据，可继续。"
    elif added_ids or state.shared_knowledge.source_memories:
        layer.coverage_status = CoverageStatus.DEGRADED
        action = AgentAction.DEGRADE
        reason = f"{layer.title} 有材料但仍偏薄，降级继续并保留缺口。"
    else:
        layer.coverage_status = CoverageStatus.NEEDS_MORE
        action = AgentAction.SEARCH_AGAIN
        reason = f"{layer.title} 缺少可用材料，需要继续调研。"
    state.add_decision(AgentDecision(
        action=action,
        reason=reason,
        layer_id=layer_id,
        coverage_gaps=state.layer_coverage_gaps(layer_id),
    ))
