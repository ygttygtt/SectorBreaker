"""Modern LangGraph workflow with typed state and explicit node/edge graph.

LangGraph 1.x pattern:
- TypedDict state schema
- Node functions return partial state updates
- add_node / add_edge / add_conditional_edges
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable, Awaitable, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from backend.app.providers.counterevidence import HeuristicCounterevidenceProvider
from backend.app.providers.interfaces import (
    ChatMessage,
    ContentExtractionProvider,
    LLMProvider,
    SearchProvider,
    SearchQuery,
)
from backend.app.providers.source_packs import blocked_domains_for_market, reliable_domains_for_market
from backend.app.providers.source_verification import HeuristicSourceVerificationProvider
from backend.app.graph.planner import build_supervisor_plan
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ClaimStrength,
    ClaimType,
    EvidenceClaim,
    EvidenceItem,
    KnowledgeMapOutput,
    MarketAnalysisOutput,
    PlayerAnalysisOutput,
    QAReport,
    ResearchGate,
    ResearchFrameOutput,
    ResearchProject,
    ResearchState,
    RunEvent,
    RunStatus,
    ScopeAnalysisOutput,
    SourceChannel,
    SourcePolicy,
    SourceQuality,
    SourceType,
    SupervisorPlan,
    SynthesisOutput,
    TransactionAnalysisOutput,
    VerificationStatus,
)

# ── Types ──────────────────────────────────────────────────────

EventEmitter = Callable[[RunEvent], Awaitable[None]]


class WorkflowState(TypedDict, total=False):
    """Typed state for the LangGraph workflow."""
    project: dict[str, Any]
    project_id: str
    current_gate: str
    evidence: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    supervisor_plan: dict[str, Any] | None
    coverage_checklist: dict[str, bool]
    qa_issues: list[str]
    qa_report: dict[str, Any] | None
    user_guidance: str | None
    user_evidence_items: list[dict[str, Any]]
    seed_evidence_items: list[dict[str, Any]]
    assistant_brief: str | None


# ── Constants ──────────────────────────────────────────────────

GATE_ORDER: list[str] = [
    ResearchGate.SCOPE.value,
    ResearchGate.SUPERVISOR_PLAN.value,
    ResearchGate.SOURCE_STRATEGY.value,
    ResearchGate.EVIDENCE.value,
    "claim_extractor_gate",
    "counterevidence_gate",
    ResearchGate.EVIDENCE_LEDGER.value,
    ResearchGate.RESEARCH_FRAME.value,
    "market_gate",
    "player_gate",
    "transaction_gate",
    "synthesis",
    ResearchGate.KNOWLEDGE_MAP.value,
    "qa_critic",
    ResearchGate.EXPORT.value,
]

HUMAN_REVIEW_GATES: set[str] = {
    ResearchGate.SUPERVISOR_PLAN.value,
}

_LLM_CONCURRENCY = 3
_llm_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)
    return _llm_semaphore


# ── Helpers ────────────────────────────────────────────────────

async def _emit(emitter: EventEmitter | None, event: RunEvent) -> None:
    if emitter is not None:
        await emitter(event)


async def _llm_generate(
    llm_provider: LLMProvider | None,
    system_prompt: str,
    user_prompt: str,
    response_schema: type[Any],
    emitter: EventEmitter | None,
    gate: str,
    agent: str,
    retries: int = 2,
) -> Any:
    if llm_provider is None:
        raise RuntimeError("LLM 未配置。请先在页面右下角点击「LLM 设置」配置 API 地址和密钥。")
    last_error = None
    for attempt in range(retries):
        try:
            return await llm_provider.complete_structured(
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_prompt),
                ],
                response_schema=response_schema,
            )
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                await _emit(emitter, RunEvent(
                    event_type="error", gate=gate, agent=agent,
                    message=f"LLM 调用失败（第 {attempt+1} 次），重试中... ({exc})",
                ))
                await asyncio.sleep(2)
    raise last_error


def _evidence_ids(state: WorkflowState) -> list[str]:
    return [item["id"] for item in state.get("evidence", [])]


def _merge_evidence_items(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = list(existing)
    seen_ids = {item.get("id") for item in existing if item.get("id")}
    for item in incoming:
        item_id = item.get("id")
        if item_id and item_id in seen_ids:
            continue
        merged.append(item)
        if item_id:
            seen_ids.add(item_id)
    return merged


def _claim_texts(item: dict[str, Any]) -> list[tuple[str, str]]:
    claims = item.get("claims") or []
    pairs: list[tuple[str, str]] = []
    for claim in claims:
        claim_id = claim.get("claim_id")
        claim_text = claim.get("text")
        if claim_id and claim_text:
            pairs.append((claim_id, claim_text))
    if not pairs and item.get("snippet"):
        pairs.append((f"CL-{item.get('id', 'UNKNOWN')}", item["snippet"]))
    return pairs


def _plan_from_state(state: WorkflowState) -> SupervisorPlan | None:
    raw = state.get("supervisor_plan")
    if not raw:
        return None
    return SupervisorPlan(**raw)


def _project_from_state(state: WorkflowState) -> ResearchProject:
    return ResearchProject(**state["project"])


def _source_policy_from_project(project: dict[str, Any]) -> SourcePolicy:
    return SourcePolicy(project.get("source_policy") or SourcePolicy.RELIABLE_FIRST.value)


def search_constraints_for_policy(
    project: dict[str, Any],
    *,
    verification: bool = False,
    preferred_domains: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    policy = _source_policy_from_project(project)
    market_scope = project.get("market_scope")

    if policy == SourcePolicy.OPEN_WEB:
        return preferred_domains or [], []

    if policy == SourcePolicy.USER_MATERIALS_ONLY:
        return [], []

    base_domains = reliable_domains_for_market(market_scope)
    blocked_domains = blocked_domains_for_market(market_scope)

    allowed_domains = list(dict.fromkeys((preferred_domains or []) + base_domains))

    if policy == SourcePolicy.RELIABLE_ONLY:
        return allowed_domains, blocked_domains

    if policy == SourcePolicy.RELIABLE_FIRST:
        if verification and preferred_domains:
            return allowed_domains, blocked_domains
        return allowed_domains, blocked_domains

    return preferred_domains or [], blocked_domains


def _source_quality_for(source_type: str | None, source_channel: SourceChannel) -> SourceQuality:
    if source_type in {"official", "government", "public_database", "company_disclosure"}:
        return SourceQuality.HIGH
    if source_type in {"industry_report", "web"}:
        return SourceQuality.MEDIUM
    if source_channel == SourceChannel.ASSISTANT_BRIEF or source_type in {"assistant_brief", "community", "media"}:
        return SourceQuality.LOW
    return SourceQuality.UNKNOWN


def _claim_from_text(evidence_id: str, text: str, claim_type: ClaimType = ClaimType.GENERAL_FACT) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=f"CL-{evidence_id}",
        text=text[:500],
        claim_type=claim_type,
        support_level=0.3,
        requires_verification=True,
        verification_status=VerificationStatus.UNVERIFIED,
        evidence_ids=[evidence_id],
    )


def _result_to_dict(llm_result: BaseModel | dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(llm_result, BaseModel):
        return llm_result.model_dump(mode="json")
    if isinstance(llm_result, dict):
        return llm_result
    return {"text": str(llm_result)}


def _extract_content(llm_result: BaseModel | dict[str, Any] | str, title: str, domain: str) -> str:
    """Extract content from LLM result, handling various response formats."""
    if isinstance(llm_result, (BaseModel, dict)):
        payload = _result_to_dict(llm_result)
        content = payload.get("content") or payload.get("text") or payload.get("result")
        if not content:
            content = json.dumps(payload, ensure_ascii=False, indent=2)
        if not str(content).startswith("#"):
            content = f"# {domain} {title}\n\n{content}"
        return str(content)
    return f"# {domain} {title}\n\n{llm_result}"


def _artifact_from_result(
    *,
    state: WorkflowState,
    project: dict[str, Any],
    art_id: str,
    art_type: ArtifactType,
    title: str,
    path: str,
    result: BaseModel | dict[str, Any] | str,
) -> list[Artifact]:
    ev_ids = _evidence_ids(state)
    payload = _result_to_dict(result)
    if "hypotheses" in payload:
        from backend.app.exporters import cards as card_gen
        card_map = card_gen.generate_opportunity_cards(project["domain"], payload, project["title"], ev_ids)
        card_dir = Path(path).parent.as_posix() if Path(path).suffix else path
        return [
            Artifact(
                id=f"{art_id}-{card_name}",
                project_id=state["project_id"],
                artifact_type=art_type,
                title=f"{title}/{card_name}",
                content_path=f"{card_dir}/{card_name}.md",
                content=card_content,
                source_evidence_ids=ev_ids,
            )
            for card_name, card_content in card_map.items()
        ]
    content = _extract_content(result, title, project["domain"])
    return [
        Artifact(
            id=art_id,
            project_id=state["project_id"],
            artifact_type=art_type,
            title=title,
            content_path=path,
            content=content,
            source_evidence_ids=ev_ids,
        )
    ]


_STRONG_FACT_MARKERS = (
    "%",
    "％",
    "亿元",
    "亿美元",
    "cagr",
    "market size",
    "市场规模",
    "增长率",
    "同比",
    "环比",
    "份额",
    "排名",
    "超过",
    "达到",
    "预计",
    "预测",
)


def _artifact_contains_strong_fact_claim(content: str | None) -> bool:
    if not content:
        return False
    lowered = content.lower()
    return any(marker in lowered for marker in _STRONG_FACT_MARKERS)


_CONFLICT_MARKERS = (
    "反驳",
    "质疑",
    "争议",
    "冲突",
    "相反",
    "不一致",
    "风险",
    "challenge",
    "challenged",
    "dispute",
    "disputed",
    "contradict",
    "conflict",
    "risk",
)


def _has_conflict_signal(*texts: str | None) -> bool:
    combined = " ".join(text for text in texts if text).lower()
    return any(marker in combined for marker in _CONFLICT_MARKERS)


def _is_acceptable_fact_support(item: dict[str, Any], policy: SourcePolicy) -> bool:
    if item.get("source_channel") == SourceChannel.SYSTEM.value:
        return False
    if item.get("needs_counterevidence"):
        return False
    if item.get("verification_status") in {VerificationStatus.UNVERIFIED.value, VerificationStatus.CONFLICTING.value}:
        return False
    if "marketing_like=true" in str(item.get("bias_risk") or ""):
        return False

    quality = item.get("source_quality")
    if policy == SourcePolicy.RELIABLE_ONLY:
        return quality == SourceQuality.HIGH.value and item.get("source_type") in {
            SourceType.OFFICIAL.value,
            SourceType.GOVERNMENT.value,
            SourceType.PUBLIC_DATABASE.value,
            SourceType.COMPANY_DISCLOSURE.value,
            SourceType.INDUSTRY_REPORT.value,
        }

    return quality in {SourceQuality.HIGH.value, SourceQuality.MEDIUM.value}


def _artifact_unsupported_claim_ids(
    artifacts: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    policy: SourcePolicy,
) -> list[str]:
    evidence_by_id = {item.get("id"): item for item in evidence if item.get("id")}
    unsupported: list[str] = []
    for artifact in artifacts:
        if not _artifact_contains_strong_fact_claim(artifact.get("content")):
            continue
        linked = [
            evidence_by_id[evidence_id]
            for evidence_id in artifact.get("source_evidence_ids", [])
            if evidence_id in evidence_by_id
        ]
        if not any(_is_acceptable_fact_support(item, policy) for item in linked):
            unsupported.append(artifact.get("id", "UNKNOWN"))
    return unsupported


def _default_plan() -> dict[str, list[str]]:
    return {
        "sections": [
            "行业定义与边界",
            "市场现状与增长驱动",
            "玩家角色与交易单位",
            "内容渠道与信任资产",
            "机会假设与验证动作",
        ],
        "key_questions": [
            "这个领域的用户为什么付费？",
            "哪些数据口径容易混淆？",
            "哪些环节最影响信任和转化？",
        ],
    }


def next_gate(current: str) -> str | None:
    try:
        idx = GATE_ORDER.index(current)
        if idx + 1 < len(GATE_ORDER):
            return GATE_ORDER[idx + 1]
    except ValueError:
        pass
    return None


# ── Node functions (modern LangGraph pattern) ─────────────────
# Each node: receives state dict, returns partial state update dict


def make_nodes(
    llm_provider: LLMProvider | None = None,
    search_provider: SearchProvider | None = None,
    content_extraction_provider: ContentExtractionProvider | None = None,
    emitter: EventEmitter | None = None,
) -> dict[str, Callable]:
    """Create all node functions with dependencies bound via closure."""
    counterevidence_provider = HeuristicCounterevidenceProvider()
    source_verifier = HeuristicSourceVerificationProvider()

    async def scope_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.SCOPE.value

        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Scope Agent",
            message=f"正在确认研究范围：{project['domain']}",
        ))

        # Inject user evidence
        evidence = list(state.get("evidence", []))
        evidence = _merge_evidence_items(evidence, state.get("seed_evidence_items", []))
        for item in state.get("user_evidence_items", []):
            evidence = _merge_evidence_items(evidence, [EvidenceItem(
                id=f"EV-USER-{item.get('id', 'SUPPLEMENT')}",
                project_id=state["project_id"],
                source_channel=SourceChannel.USER_UPLOAD,
                source_policy=project.get("source_policy"),
                source_quality=SourceQuality.MEDIUM,
                claim_strength=ClaimStrength.FACT,
                source_title=item.get("source_title", "用户补充信息"),
                snippet=item.get("snippet", ""),
                summary=item.get("summary"),
                confidence=item.get("confidence", 0.8),
                verification_status=VerificationStatus.UNVERIFIED,
            ).model_dump(mode="json")])

        evidence = _merge_evidence_items(evidence, [EvidenceItem(
            id="EV-USER-SCOPE",
            project_id=state["project_id"],
            source_title="User project scope",
            source_channel=SourceChannel.SYSTEM,
            source_policy=project.get("source_policy"),
            source_quality=SourceQuality.HIGH,
            claim_strength=ClaimStrength.FACT,
            snippet=f"User wants to research {project['domain']} with {project['market_scope']} scope.",
            summary="User-provided scope and intent.",
            confidence=1.0,
            verification_status=VerificationStatus.UNVERIFIED,
        ).model_dump(mode="json")])

        # LLM scope analysis
        await _emit(emitter, RunEvent(
            event_type="node_progress", gate=gate, step="scope_analysis", agent="Research Planner",
            message="正在分析领域边界和研究范围...",
            progress_current=1, progress_total=2,
        ))

        scope_analysis = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是行业研究规划 Agent。用户想研究一个领域，你需要：\n"
                "1. 分析这个领域的边界和定义\n"
                "2. 列出研究该领域最应先搞清楚的 10 个关键问题，每个说明：为什么重要、应该去哪里找答案、"
                "常见误判是什么、如果只用1小时应该优先查到什么程度\n"
                "3. 列出常见数据口径问题：指标名称、常见统计口径、容易混淆的地方、"
                "适合回答什么问题、不适合回答什么问题、建议优先查证的数据来源\n"
                "只返回 JSON，字段：domain_definition, boundaries, common_confusions, "
                "key_questions（列表，每个含 question/importance/source/common_mistake/priority_1h）, "
                "data_caliber（列表，每个含 metric/caliber/confusion/suitable_for/not_suitable_for/recommended_source）。"
            ),
            user_prompt=(
                f"领域：{project['domain']}\n"
                f"市场范围：{project['market_scope']}\n"
                f"研究深度：{project['depth']}\n"
                f"{'用户补充：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            emitter=emitter, gate=gate, agent="Research Planner",
            response_schema=ScopeAnalysisOutput,
        )

        # Build scope artifact
        definition = scope_analysis.domain_definition
        boundaries = scope_analysis.boundaries
        confusions = scope_analysis.common_confusions
        questions_md = "".join(
            (
                f"### {q.question}\n"
                f"- **为什么重要**：{q.importance}\n"
                f"- **去哪找答案**：{q.source}\n"
                f"- **常见误判**：{q.common_mistake}\n"
                f"- **1小时优先级**：{q.priority_1h}\n\n"
            )
            for q in scope_analysis.key_questions
        )
        caliber_md = "".join(
            (
                f"| {c.metric} | {c.caliber} | {c.confusion} | {c.suitable_for} | "
                f"{c.not_suitable_for} | {c.recommended_source} |\n"
            )
            for c in scope_analysis.data_caliber
        )
        if definition or boundaries:
            content = (
                f"# {project['domain']} 研究范围分析\n\n"
                f"## 领域定义\n\n{definition}\n\n"
                f"## 边界说明\n\n{boundaries}\n\n"
                f"## 常见混淆点\n\n" + "\n".join(f"- {c}" for c in confusions) + "\n\n"
                f"## 关键问题（10个）\n\n{questions_md}\n"
                f"## 数据口径\n\n| 指标 | 统计口径 | 容易混淆 | 适合回答 | 不适合回答 | 建议数据来源 |\n"
                f"|------|---------|---------|---------|-----------|------------|\n{caliber_md}\n"
            )
        else:
            content = (
                f"# {project['domain']} 研究范围分析\n\n"
                f"{json.dumps(scope_analysis.model_dump(mode='json'), ensure_ascii=False, indent=2)}"
            )

        artifacts = list(state.get("artifacts", []))
        artifacts.append(Artifact(
            id="ART-SCOPE-ANALYSIS", project_id=state["project_id"],
            artifact_type=ArtifactType.RESEARCH_FRAME, title="研究范围分析",
            content_path="00-研究范围/scope-analysis.md", content=content,
            source_evidence_ids=[item["id"] for item in evidence],
        ).model_dump(mode="json"))

        await _emit(emitter, RunEvent(
            event_type="artifact_created", gate=gate, agent="Research Planner",
            message=f"范围分析完成：{content[:80]}...",
        ))
        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Scope Agent", message="研究范围已确认",
            progress_current=2, progress_total=2,
        ))

        return {
            "current_gate": ResearchGate.SUPERVISOR_PLAN.value,
            "evidence": evidence,
            "artifacts": artifacts,
            "coverage_checklist": {
                **state.get("coverage_checklist", {}),
                "scope_confirmed": True,
                "research_frame": False,
                "knowledge_map": False,
                "opportunity_map": False,
            },
        }

    async def supervisor_plan_gate(state: WorkflowState) -> dict[str, Any]:
        project = _project_from_state(state)
        gate = ResearchGate.SUPERVISOR_PLAN.value
        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Supervisor Agent",
            message="正在生成可解释研究作战计划",
        ))

        has_user_materials = bool(state.get("user_evidence_items"))
        has_assistant_brief = bool(state.get("assistant_brief"))
        plan = build_supervisor_plan(
            project,
            user_guidance=state.get("user_guidance"),
            has_assistant_brief=has_assistant_brief,
            has_user_materials=has_user_materials,
        )

        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Supervisor Agent",
            message=f"主管计划已生成：启用 {len(plan.selected_agents)} 个 Agent，跳过 {len(plan.skipped_agents)} 个 Agent",
            data=plan.model_dump(mode="json"),
            progress_current=1, progress_total=1,
        ))
        return {
            "current_gate": ResearchGate.SOURCE_STRATEGY.value,
            "supervisor_plan": plan.model_dump(mode="json"),
        }

    async def source_strategy_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        plan = _plan_from_state(state)
        gate = ResearchGate.SOURCE_STRATEGY.value
        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Source Strategy Agent",
            message=f"正在应用信源模式：{project.get('source_policy', SourcePolicy.RELIABLE_FIRST.value)}",
            data=plan.model_dump(mode="json") if plan else None,
        ))

        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Source Strategy Agent",
            message=plan.source_policy_reason if plan else "信源策略已确认",
            progress_current=1, progress_total=1,
        ))
        return {"current_gate": ResearchGate.EVIDENCE.value}

    async def evidence_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.EVIDENCE.value
        source_policy = _source_policy_from_project(project)

        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Source Intake",
            message="正在接入搜索、用户材料和外部报告线索",
        ))

        evidence = list(state.get("evidence", []))
        if state.get("assistant_brief"):
            brief_id = "EV-ASSISTANT-BRIEF-001"
            brief_text = state["assistant_brief"] or ""
            evidence.append(EvidenceItem(
                id=brief_id,
                project_id=state["project_id"],
                source_title="外部 AI 调研报告",
                source_type="assistant_brief",
                source_channel=SourceChannel.ASSISTANT_BRIEF,
                source_policy=source_policy.value,
                raw_excerpt=brief_text[:3000],
                snippet=brief_text[:800],
                summary="用户手动提供的外部 AI 调研报告，仅作为线索。",
                claims=[
                    _claim_from_text(brief_id, line.strip())
                    for line in brief_text.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ][:8],
                source_quality=SourceQuality.LOW,
                claim_strength=ClaimStrength.OPINION,
                bias_risk="外部 AI 报告可能混入二手资料、营销内容或未标注来源的判断。",
                needs_counterevidence=True,
                collected_by="assistant_brief_agent",
                confidence=0.25,
                verification_status=VerificationStatus.UNVERIFIED,
            ).model_dump(mode="json"))
            await _emit(emitter, RunEvent(
                event_type="claim_extracted", gate=gate, agent="Assistant Brief Agent",
                message="外部 AI 报告已拆为低可信线索，后续关键结论需验证",
                progress_current=1, progress_total=4,
            ))

        if source_policy == SourcePolicy.USER_MATERIALS_ONLY:
            await _emit(emitter, RunEvent(
                event_type="node_skipped", gate=gate, agent="Search Scout",
                message="当前为仅用户材料模式，跳过开放搜索",
                progress_current=2, progress_total=4,
            ))
            return {"current_gate": ResearchGate.EVIDENCE_LEDGER.value, "evidence": evidence}

        search_queries = [
            f"{project['domain']} 行业概况 市场规模 趋势",
            f"{project['domain']} 主要玩家 竞争格局",
            f"{project['domain']} 用户痛点 机会",
        ]
        allowed_domains, blocked_domains = search_constraints_for_policy(project)

        for query_idx, query_text in enumerate(search_queries):
            await _emit(emitter, RunEvent(
                event_type="node_progress", gate=gate, step=f"search_{query_idx}", agent="Search Scout",
                message=f"正在搜索：{query_text}",
                progress_current=query_idx + 1, progress_total=len(search_queries),
            ))
            if search_provider is not None:
                try:
                    results = await search_provider.search(
                        SearchQuery(
                            query=query_text,
                            market_scope=project["market_scope"],
                            max_results=5,
                            allowed_domains=allowed_domains,
                            blocked_domains=blocked_domains,
                        )
                    )
                    for index, result in enumerate(results, start=1):
                        evidence_id = f"EV-SEARCH-{query_idx}-{index:03d}"
                        assessment = await source_verifier.assess_source(
                            url=result.url,
                            title=result.title,
                            snippet=result.snippet,
                            extracted_text=None,
                            source_policy=source_policy.value,
                        )
                        verification_status = VerificationStatus(
                            assessment.recommended_verification_status
                            or VerificationStatus.PARTIALLY_VERIFIED.value
                        )
                        source_quality = SourceQuality(assessment.source_quality)
                        evidence.append(EvidenceItem(
                            id=evidence_id,
                            project_id=state["project_id"],
                            source_title=result.title, source_url=result.url, source_type=assessment.source_type,
                            source_channel=SourceChannel.SEARCH,
                            source_policy=source_policy.value,
                            snippet=result.snippet, summary=result.snippet,
                            claims=[
                                _claim_from_text(
                                    evidence_id,
                                    result.snippet,
                                )
                            ],
                            source_quality=source_quality,
                            claim_strength=(
                                ClaimStrength.FACT
                                if verification_status == VerificationStatus.VERIFIED
                                else ClaimStrength.OPINION
                            ),
                            bias_risk=assessment.reliability_notes,
                            needs_counterevidence=(
                                assessment.is_marketing_like
                                or source_quality in {SourceQuality.LOW, SourceQuality.UNKNOWN}
                                or verification_status == VerificationStatus.UNVERIFIED
                            ),
                            collected_by="search_scout",
                            confidence=(
                                0.82
                                if verification_status == VerificationStatus.VERIFIED
                                else 0.55 if source_quality == SourceQuality.MEDIUM else 0.35
                            ),
                            verification_status=verification_status,
                        ).model_dump(mode="json"))
                        await _emit(emitter, RunEvent(
                            event_type="evidence_collected", gate=gate, agent="Search Scout",
                            message=f"找到：{result.title}",
                            data={
                                "evidence_id": evidence_id,
                                "source_quality": source_quality.value,
                                "source_type": assessment.source_type,
                                "verification_status": verification_status.value,
                                "is_marketing_like": assessment.is_marketing_like,
                            },
                        ))
                except Exception as exc:
                    await _emit(emitter, RunEvent(
                        event_type="error", gate=gate, agent="Search Scout", message=f"搜索失败：{exc}",
                    ))
            else:
                await _emit(emitter, RunEvent(
                    event_type="node_degraded", gate=gate, step=f"search_{query_idx}", agent="Search Scout",
                    message="未配置搜索提供商，跳过",
                    severity="warning",
                ))

        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Source Intake", message="证据接入完成",
        ))
        return {"current_gate": ResearchGate.EVIDENCE_LEDGER.value, "evidence": evidence}

    async def evidence_ledger_gate(state: WorkflowState) -> dict[str, Any]:
        gate = ResearchGate.EVIDENCE_LEDGER.value
        evidence = list(state.get("evidence", []))
        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Evidence Curator",
            message=f"正在整理证据账本：{len(evidence)} 条材料",
        ))

        high = medium = low = counter = 0
        curated: list[dict[str, Any]] = []
        for item in evidence:
            quality = item.get("source_quality", SourceQuality.UNKNOWN.value)
            if quality == SourceQuality.HIGH.value:
                high += 1
            elif quality == SourceQuality.MEDIUM.value:
                medium += 1
            elif quality == SourceQuality.LOW.value:
                low += 1

            weak_source = item.get("source_type") in {"assistant_brief", "community", "media"}
            critical_claim = any(
                claim.get("claim_type") in {
                    ClaimType.MARKET_SIZE.value,
                    ClaimType.GROWTH_TREND.value,
                    ClaimType.PLAYER_STATUS.value,
                    ClaimType.OPPORTUNITY.value,
                    ClaimType.POLICY_RISK.value,
                }
                for claim in item.get("claims", [])
            )
            if weak_source or critical_claim or item.get("needs_counterevidence"):
                item["needs_counterevidence"] = True
                counter += 1
            curated.append(item)

        await _emit(emitter, RunEvent(
            event_type="node_progress", gate=gate, agent="Evidence Curator",
            message=f"证据评级：高 {high} / 中 {medium} / 低 {low}，需反证 {counter}",
            data={"high": high, "medium": medium, "low": low, "counterevidence": counter},
            progress_current=1, progress_total=2,
        ))

        if counter:
            await _emit(emitter, RunEvent(
                event_type="node_progress", gate=gate, agent="Counterevidence Agent",
                message=f"发现 {counter} 条需要反证或复核的线索，已标记为待验证",
                progress_current=2, progress_total=2,
            ))
        else:
            await _emit(emitter, RunEvent(
                event_type="node_skipped", gate=gate, agent="Counterevidence Agent",
                message="暂无触发反证的关键低可信结论",
            ))

        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Evidence Ledger",
            message="证据账本已更新",
        ))
        return {
            "current_gate": ResearchGate.KNOWLEDGE_MAP.value,
            "evidence": curated,
            "coverage_checklist": {
                **state.get("coverage_checklist", {}),
                "evidence_ledger": True,
                "counterevidence_marked": True,
            },
        }

    async def claim_extractor_gate(state: WorkflowState) -> dict[str, Any]:
        gate = "claim_extractor"
        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Claim Extractor",
            message="正在把外部报告与用户材料拆成可验证主张",
        ))
        evidence = list(state.get("evidence", []))
        extracted = 0
        for item in evidence:
            if item.get("claims"):
                extracted += len(item["claims"])
            elif item.get("snippet"):
                claim = _claim_from_text(item["id"], item["snippet"])
                item["claims"] = [claim.model_dump(mode="json")]
                extracted += 1
        await _emit(emitter, RunEvent(
            event_type="claim_extracted", gate=gate, agent="Claim Extractor",
            message=f"已拆出 {extracted} 条可验证主张",
            progress_current=1, progress_total=1,
        ))
        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Claim Extractor",
            message="Claim 拆解完成",
        ))
        return {"evidence": evidence}

    async def counterevidence_gate(state: WorkflowState) -> dict[str, Any]:
        gate = "counterevidence"
        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Counterevidence Agent",
            message="正在对关键主张做反证核对",
        ))
        evidence = list(state.get("evidence", []))
        counter = 0
        verification_tasks_created = 0
        verification_evidence: list[dict[str, Any]] = []
        existing_ids = {item.get("id") for item in evidence if item.get("id")}
        for item in evidence:
            if not item.get("needs_counterevidence"):
                continue

            counter += 1
            item["verification_status"] = VerificationStatus.PARTIALLY_VERIFIED.value
            for claim_id, claim_text in _claim_texts(item):
                tasks = await counterevidence_provider.build_verification_tasks(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    market_scope=state["project"]["market_scope"],
                )
                verification_tasks_created += len(tasks)
                for task in tasks:
                    await _emit(emitter, RunEvent(
                        event_type="verification_task_created",
                        gate=gate,
                        agent="Counterevidence Agent",
                        message=f"已为主张创建验证任务：{task.verification_goal}",
                        data={
                            "task_id": task.task_id,
                            "claim_id": task.claim_id,
                            "query_variants": task.query_variants,
                            "preferred_domains": task.preferred_domains,
                        },
                    ))
                    if search_provider is None:
                        continue

                    query_text = task.query_variants[0] if task.query_variants else claim_text
                    allowed_domains, blocked_domains = search_constraints_for_policy(
                        state["project"],
                        verification=True,
                        preferred_domains=task.preferred_domains or [],
                    )
                    try:
                        results = await search_provider.search(
                            SearchQuery(
                                query=query_text,
                                market_scope=state["project"]["market_scope"],
                                max_results=3,
                                allowed_domains=allowed_domains,
                                blocked_domains=blocked_domains,
                            )
                        )
                    except Exception as exc:
                        await _emit(emitter, RunEvent(
                            event_type="error",
                            gate=gate,
                            agent="Counterevidence Agent",
                            message=f"验证搜索失败：{exc}",
                        ))
                        continue

                    for index, result in enumerate(results, start=1):
                        evidence_id = f"EV-VERIFY-{task.task_id}-{index:03d}"
                        if evidence_id in existing_ids:
                            continue
                        extracted_page = None
                        if content_extraction_provider is not None and result.url:
                            try:
                                extracted_page = await content_extraction_provider.extract_url(result.url)
                            except Exception as exc:
                                await _emit(emitter, RunEvent(
                                    event_type="node_degraded",
                                    gate=gate,
                                    agent="Content Extraction",
                                    message=f"正文抽取失败，降级使用 snippet：{exc}",
                                    severity="warning",
                                ))
                        assessment = await source_verifier.assess_source(
                            url=result.url,
                            title=extracted_page.title if extracted_page and extracted_page.title else result.title,
                            snippet=result.snippet,
                            extracted_text=extracted_page.raw_text if extracted_page else None,
                            source_policy=state["project"].get("source_policy"),
                        )
                        if task.verification_goal == "challenge" and not _has_conflict_signal(
                            result.title,
                            result.snippet,
                            extracted_page.raw_text if extracted_page else None,
                        ):
                            continue
                        verification_status = (
                            VerificationStatus(assessment.recommended_verification_status)
                            if task.verification_goal == "corroborate"
                            else VerificationStatus.CONFLICTING
                        )
                        claim_note = (
                            "自动反证搜索得到的补充支持线索"
                            if task.verification_goal == "corroborate"
                            else "自动反证搜索得到的潜在冲突线索"
                        )
                        snippet = result.snippet
                        raw_excerpt = result.snippet
                        summary = f"{task.verification_goal} result for {claim_id}"
                        if extracted_page and extracted_page.raw_text:
                            raw_excerpt = extracted_page.raw_text[:4000]
                            snippet = extracted_page.raw_text[:800]
                            summary = (
                                f"{task.verification_goal} result for {claim_id}; "
                                f"extracted via {extracted_page.extraction_provider}"
                            )
                        verification_item = EvidenceItem(
                            id=evidence_id,
                            project_id=state["project_id"],
                            source_title=extracted_page.title if extracted_page and extracted_page.title else result.title,
                            source_url=result.url,
                            source_type=assessment.source_type,
                            source_channel=SourceChannel.SEARCH,
                            source_policy=state["project"].get("source_policy"),
                            raw_excerpt=raw_excerpt,
                            snippet=snippet,
                            summary=summary,
                            claims=[
                                EvidenceClaim(
                                    claim_id=f"CL-{evidence_id}",
                                    text=claim_text,
                                    claim_type=ClaimType.GENERAL_FACT,
                                    support_level=0.35 if task.verification_goal == "corroborate" else 0.2,
                                    requires_verification=True,
                                    verification_status=verification_status,
                                    evidence_ids=[evidence_id],
                                    notes=claim_note,
                                )
                            ],
                            source_quality=SourceQuality(assessment.source_quality),
                            claim_strength=(
                                ClaimStrength.FACT
                                if (
                                    task.verification_goal == "corroborate"
                                    and verification_status == VerificationStatus.VERIFIED
                                    and assessment.source_quality == SourceQuality.HIGH.value
                                )
                                else ClaimStrength.OPINION
                            ),
                            bias_risk=assessment.reliability_notes or (
                                "Needs manual corroboration"
                                if task.verification_goal == "corroborate"
                                else "Potential counterevidence or contradiction"
                            ),
                            needs_counterevidence=(
                                task.verification_goal != "challenge"
                                and assessment.recommended_verification_status != VerificationStatus.VERIFIED.value
                            ),
                            collected_by="counterevidence_search",
                            confidence=0.75 if extracted_page and assessment.source_quality == SourceQuality.HIGH.value else (
                                0.55 if task.verification_goal == "corroborate" else 0.4
                            ),
                            verification_status=verification_status,
                        ).model_dump(mode="json")
                        verification_evidence.append(verification_item)
                        link_field = (
                            "corroborating_evidence_ids"
                            if task.verification_goal == "corroborate"
                            else "conflicting_evidence_ids"
                        )
                        linked_ids = list(item.get(link_field) or [])
                        if evidence_id not in linked_ids:
                            linked_ids.append(evidence_id)
                        item[link_field] = linked_ids
                        for claim in item.get("claims", []):
                            counter_ids = list(claim.get("counterevidence_ids") or [])
                            if evidence_id not in counter_ids:
                                counter_ids.append(evidence_id)
                            claim["counterevidence_ids"] = counter_ids
                        existing_ids.add(evidence_id)
                        await _emit(emitter, RunEvent(
                            event_type="counterevidence_found",
                            gate=gate,
                            agent="Counterevidence Agent",
                            message=f"验证搜索补充来源：{result.title}",
                            data={
                                "task_id": task.task_id,
                                "verification_goal": task.verification_goal,
                                "evidence_id": evidence_id,
                                "url": result.url,
                            },
                        ))

        evidence = _merge_evidence_items(evidence, verification_evidence)
        event_type = "node_completed" if counter == 0 else "node_degraded"
        event_payload: dict[str, Any] = {
            "event_type": event_type,
            "gate": gate,
            "agent": "Counterevidence Agent",
            "message": (
                "反证核对完成"
                if counter == 0
                else f"已为 {counter} 条线索创建 {verification_tasks_created} 个验证任务，补充 {len(verification_evidence)} 条验证证据"
            ),
        }
        if counter:
            event_payload["severity"] = "warning"
        await _emit(emitter, RunEvent(**event_payload))
        return {"evidence": evidence}

    async def research_frame_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.RESEARCH_FRAME.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate, message="正在生成研究框架",
        ))

        plan = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是行业研究规划 Agent。为用户指定的行业生成研究框架。"
                "只返回 JSON，字段：sections（研究板块列表）, key_questions（关键问题列表）, "
                "learning_path（学习路径列表）。"
            ),
            user_prompt=(
                f"为 {project['domain']} 生成研究框架。"
                f"市场范围：{project['market_scope']}。"
                f"{'用户补充方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            response_schema=ResearchFrameOutput,
            emitter=emitter, gate=gate, agent="Research Planner",
        )

        sections = [item for item in plan.sections if item]
        key_questions = [item for item in plan.key_questions if item]

        if not sections:
            default = _default_plan()
            sections = default["sections"]
            key_questions = key_questions or default["key_questions"]

        body = (
            f"# {project['domain']} 研究框架\n\n## 先学什么\n\n"
            + "\n".join(f"- {s}" for s in sections)
            + "\n\n## 关键问题\n\n"
            + "\n".join(f"- {q}" for q in key_questions) + "\n"
        )

        artifacts = list(state.get("artifacts", []))
        artifacts.append(Artifact(
            id="ART-RESEARCH-FRAME", project_id=state["project_id"],
            artifact_type=ArtifactType.RESEARCH_FRAME, title="研究框架",
            content_path="00-研究框架/research-frame.md", content=body,
            source_evidence_ids=_evidence_ids(state),
        ).model_dump(mode="json"))

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate, message="研究框架生成完成",
        ))
        return {
            "artifacts": artifacts,
            "coverage_checklist": {
                **state.get("coverage_checklist", {}),
                "research_frame": bool(sections and key_questions),
            },
        }

    async def knowledge_map_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.KNOWLEDGE_MAP.value

        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Business Analysis Fan-out",
            message="正在整理前面各业务子 Agent 的结果，沉淀知识地图",
        ))
        result = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是知识管理 Agent。根据已经产出的市场、玩家、交易单位、机会等研究结果，"
                "生成行业地图和知识卡片模板。只返回 JSON，字段：title, content（Markdown）。"
            ),
            user_prompt=(
                f"行业：{project['domain']}\n市场范围：{project['market_scope']}\n"
                f"已有产物：{', '.join(a.get('title', '') for a in state.get('artifacts', []))}\n"
                f"证据数：{len(state.get('evidence', []))}\n"
                f"{'用户方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            response_schema=KnowledgeMapOutput,
            emitter=emitter, gate=gate, agent="Knowledge Mapper",
        )
        new_artifacts = list(state.get("artifacts", []))
        new_artifacts.append(
            Artifact(
                id="ART-INDUSTRY-MAP",
                project_id=state["project_id"],
                artifact_type=ArtifactType.INDUSTRY_MAP,
                title="行业地图",
                content_path="01-行业地图/00-行业总览.md",
                content=_extract_content(result, "行业地图", project["domain"]),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json")
        )
        new_artifacts.append(
            Artifact(
                id="ART-KNOWLEDGE-CARD-TEMPLATE",
                project_id=state["project_id"],
                artifact_type=ArtifactType.EXPORT_MANIFEST,
                title="知识卡片模板",
                content_path="06-知识卡片模板.md",
                content=_extract_content(result, "知识卡片模板", project["domain"]),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json")
        )

        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Knowledge Mapper", message="知识地图收口完成",
        ))
        return {
            "current_gate": "qa_critic",
            "artifacts": new_artifacts,
            "coverage_checklist": {
                **state.get("coverage_checklist", {}),
                "research_frame": True,
                "knowledge_map": True,
                "market": True,
                "player": True,
                "transaction": True,
                "opportunity_map": True,
            },
        }

    async def market_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = "market_agent"
        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Market Agent",
            message="正在分析市场规模、增长驱动与约束",
        ))
        artifacts = list(state.get("artifacts", []))
        if not any(item.get("id") == "ART-RESEARCH-FRAME" for item in artifacts):
            default = _default_plan()
            artifacts.append(
                Artifact(
                    id="ART-RESEARCH-FRAME",
                    project_id=state["project_id"],
                    artifact_type=ArtifactType.RESEARCH_FRAME,
                    title="研究框架",
                    content_path="00-研究框架/research-frame.md",
                    content=(
                        f"# {project['domain']} 研究框架\n\n## 先学什么\n\n"
                        + "\n".join(f"- {s}" for s in default["sections"])
                        + "\n\n## 关键问题\n\n"
                        + "\n".join(f"- {q}" for q in default["key_questions"])
                        + "\n"
                    ),
                    source_evidence_ids=_evidence_ids(state),
                ).model_dump(mode="json")
            )
        result = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是市场分析 Agent。为指定行业生成市场现状分析。"
                "只返回 JSON，字段：title, content（Markdown，包含市场规模、增长速度、核心细分市场、供给规模、增长驱动、限制因素、数据来源可信度、区分事实/推测/观点）。"
            ),
            user_prompt=(
                f"行业：{project['domain']}\n市场范围：{project['market_scope']}\n"
                f"研究深度：{project['depth']}\n证据数：{len(state.get('evidence', []))}\n"
                f"{'用户方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            response_schema=MarketAnalysisOutput,
            emitter=emitter, gate=gate, agent="Market Agent",
        )
        artifacts.extend(
            [
                art.model_dump(mode="json")
                for art in _artifact_from_result(
                    state=state,
                    project=project,
                    art_id="ART-MARKET-OVERVIEW",
                    art_type=ArtifactType.MARKET_OVERVIEW,
                    title="市场现状",
                    path="02-市场分析/00-市场总览.md",
                    result=result,
                )
            ]
        )
        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Market Agent",
            message="市场分析完成",
        ))
        return {"artifacts": artifacts}

    async def player_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = "player_agent"
        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Player Agent",
            message="正在分析玩家角色与竞品结构",
        ))
        result = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是竞品分析 Agent。按角色分类分析玩家：提供服务/拥有用户/拥有渠道/掌握资源/负责交付/监管/从交易赚钱。"
                "每类给代表玩家、商业价值、议价能力、新手忽略的地方。返回 JSON，字段：title, content（Markdown）。"
            ),
            user_prompt=(
                f"行业：{project['domain']}\n市场范围：{project['market_scope']}\n"
                f"研究深度：{project['depth']}\n证据数：{len(state.get('evidence', []))}\n"
                f"{'用户方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            response_schema=PlayerAnalysisOutput,
            emitter=emitter, gate=gate, agent="Player Agent",
        )
        artifacts = list(state.get("artifacts", []))
        artifacts.extend(
            [
                art.model_dump(mode="json")
                for art in _artifact_from_result(
                    state=state,
                    project=project,
                    art_id="ART-COMPETITOR-ANALYSIS",
                    art_type=ArtifactType.COMPETITOR_ANALYSIS,
                    title="竞品数据库",
                    path="03-玩家与竞品",
                    result=result,
                )
            ]
        )
        artifacts.append(
            Artifact(
                id="ART-PLAYER-MAP",
                project_id=state["project_id"],
                artifact_type=ArtifactType.PLAYER_MAP,
                title="玩家与交易单位",
                content_path="03-玩家与竞品/00-玩家总览.md",
                content=_extract_content(result, "玩家与交易单位", project["domain"]),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json")
        )
        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Player Agent",
            message="玩家分析完成",
        ))
        return {"artifacts": artifacts}

    async def transaction_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = "transaction_agent"
        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Transaction Agent",
            message="正在拆解交易单位与付费逻辑",
        ))
        result = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是商业模式分析 Agent。返回 JSON，字段：units（数组，每个含 name/why_buy/price_range/frequency/repurchase_cycle/decision_cost/delivery_difficulty/risks/margin_source/selling_points/user_keywords）。"
                "至少列出5个交易单位。"
            ),
            user_prompt=(
                f"行业：{project['domain']}\n市场范围：{project['market_scope']}\n"
                f"研究深度：{project['depth']}\n证据数：{len(state.get('evidence', []))}\n"
                f"{'用户方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            response_schema=TransactionAnalysisOutput,
            emitter=emitter, gate=gate, agent="Transaction Agent",
        )
        artifacts = list(state.get("artifacts", []))
        artifacts.extend(
            [
                art.model_dump(mode="json")
                for art in _artifact_from_result(
                    state=state,
                    project=project,
                    art_id="ART-TRANSACTION-UNITS",
                    art_type=ArtifactType.TRANSACTION_UNITS,
                    title="交易单位数据库",
                    path="02-市场分析/交易单位",
                    result=result,
                )
            ]
        )
        artifacts.append(
            Artifact(
                id="ART-REVENUE-STRUCTURE",
                project_id=state["project_id"],
                artifact_type=ArtifactType.REVENUE_STRUCTURE,
                title="收入结构",
                content_path="02-市场分析/00-收入结构.md",
                content=_extract_content(result, "收入结构", project["domain"]),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json")
        )
        artifacts.append(
            Artifact(
                id="ART-TRUST-ASSETS",
                project_id=state["project_id"],
                artifact_type=ArtifactType.TRUST_ASSETS,
                title="信任资产",
                content_path="04-内容生态/00-信任资产.md",
                content=_extract_content(result, "信任资产", project["domain"]),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json")
        )
        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Transaction Agent",
            message="交易单位分析完成",
        ))
        return {"artifacts": artifacts}

    async def synthesis_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = "synthesis"
        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="Opportunity Agent",
            message="正在汇总结论并生成机会地图",
        ))
        result = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是机会分析 Agent。基于前面的行业研究，为指定行业生成机会地图。"
                "只返回 JSON，字段：title, content（Markdown，包含至少3个机会假设，每个含机会名称、逻辑、目标用户、进入门槛、资源、风险、第一周可验证什么；必须区分事实、假设和待验证问题）。"
            ),
            user_prompt=(
                f"行业：{project['domain']}\n市场范围：{project['market_scope']}\n"
                f"证据数：{len(state.get('evidence', []))}\n"
                f"已有产物：{', '.join(a.get('title', '') for a in state.get('artifacts', []))}\n"
                f"{'用户方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            response_schema=SynthesisOutput,
            emitter=emitter, gate=gate, agent="Opportunity Agent",
        )
        artifacts = list(state.get("artifacts", []))
        artifacts.extend(
            [
                art.model_dump(mode="json")
                for art in _artifact_from_result(
                    state=state,
                    project=project,
                    art_id="ART-OPPORTUNITY-MAP",
                    art_type=ArtifactType.OPPORTUNITY_MAP,
                    title="机会地图",
                    path="05-机会与验证/00-机会总览.md",
                    result=result,
                )
            ]
        )
        artifacts.append(
            Artifact(
                id="ART-CONTENT-CHANNELS",
                project_id=state["project_id"],
                artifact_type=ArtifactType.CONTENT_CHANNELS,
                title="内容与渠道",
                content_path="04-内容生态/00-内容总览.md",
                content=_extract_content(result, "内容与渠道", project["domain"]),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json")
        )
        artifacts.append(
            Artifact(
                id="ART-CONTENT-TOPICS",
                project_id=state["project_id"],
                artifact_type=ArtifactType.CONTENT_TOPICS,
                title="高频选题分析",
                content_path="04-内容生态/00-高频选题.md",
                content=_extract_content(result, "高频选题分析", project["domain"]),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json")
        )
        artifacts.append(
            Artifact(
                id="ART-KNOWLEDGE-CARD-TEMPLATE",
                project_id=state["project_id"],
                artifact_type=ArtifactType.EXPORT_MANIFEST,
                title="知识卡片模板",
                content_path="06-知识卡片模板.md",
                content=_extract_content(result, "知识卡片模板", project["domain"]),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json")
        )
        await _emit(emitter, RunEvent(
            event_type="node_completed", gate=gate, agent="Opportunity Agent",
            message="机会综合完成",
        ))
        return {"artifacts": artifacts}

    async def qa_critic_gate(state: WorkflowState) -> dict[str, Any]:
        gate = "qa_critic"
        await _emit(emitter, RunEvent(
            event_type="node_started", gate=gate, agent="QA Critic", message="质量门检查中",
        ))

        checklist = state.get("coverage_checklist", {})
        required = ["scope_confirmed", "evidence_ledger", "research_frame", "market", "player", "transaction", "knowledge_map", "opportunity_map"]
        missing = [k for k in required if not checklist.get(k)]
        qa_issues = list(state.get("qa_issues", []))
        retry_tasks: list[str] = []
        user_action_needed: list[str] = []
        policy = _source_policy_from_project(state["project"])
        if missing:
            qa_issues.append(f"研究框架或关键产物 coverage 不完整: {', '.join(missing)}")
            retry_tasks.append("重新运行缺失 coverage 对应的 Agent。")

        unsupported = [a["id"] for a in state.get("artifacts", []) if not a.get("source_evidence_ids")]
        if unsupported:
            qa_issues.append(f"存在缺少证据引用的产物: {', '.join(unsupported)}")
            retry_tasks.append("让产物重新绑定 evidence_id 后再导出。")

        unsupported_claim_artifacts = _artifact_unsupported_claim_ids(
            state.get("artifacts", []),
            state.get("evidence", []),
            policy,
        )
        if unsupported_claim_artifacts:
            qa_issues.append(f"产物包含缺少强证据支撑的事实主张: {', '.join(unsupported_claim_artifacts[:5])}")
            retry_tasks.append("补充可靠来源并重新生成相关产物，或把这些主张降级为待验证问题。")

        weak_counter = [
            item["id"]
            for item in state.get("evidence", [])
            if item.get("needs_counterevidence")
            and item.get("verification_status") == VerificationStatus.UNVERIFIED.value
        ]
        if weak_counter:
            qa_issues.append(f"存在待反证或未验证的关键线索: {', '.join(weak_counter[:5])}")
            retry_tasks.append("对未验证关键线索运行 Counterevidence Agent 或降级为待验证问题。")

        if policy == SourcePolicy.RELIABLE_ONLY:
            disallowed = [
                item["id"]
                for item in state.get("evidence", [])
                if item.get("source_type") in {"assistant_brief", "community", "media", "web"}
                and item.get("claim_strength") in {
                    ClaimStrength.FACT.value,
                    ClaimStrength.ESTIMATE.value,
                    ClaimStrength.PREDICTION.value,
                }
                and item.get("verification_status") != VerificationStatus.CONFLICTING.value
                and item.get("collected_by") != "counterevidence_search"
            ]
            if disallowed:
                qa_issues.append(f"严格可靠模式下存在弱来源证据: {', '.join(disallowed[:5])}")
                retry_tasks.append("移除弱来源事实支撑，或切换为可靠优先模式。")

        if weak_counter:
            user_action_needed.append("如果你手头有可靠报告或公开来源，可上传补充；否则系统会把相关结论标为待验证。")

        report = QAReport(
            passed=not qa_issues,
            blocking_issues=qa_issues,
            retry_tasks=retry_tasks,
            user_action_needed=user_action_needed,
            can_continue_with_warning=(
                bool(weak_counter)
                and not missing
                and not unsupported
                and not unsupported_claim_artifacts
            ),
        )

        if qa_issues:
            await _emit(emitter, RunEvent(
                event_type="node_blocked", gate=gate, agent="QA Critic",
                message=f"质量门发现问题：{'; '.join(qa_issues)}",
                data=report.model_dump(mode="json"),
                severity="error",
            ))
        else:
            await _emit(emitter, RunEvent(
                event_type="node_completed", gate=gate, agent="QA Critic",
                message=f"质量门检查通过（{len(state.get('artifacts', []))} 个产物，{len(state.get('evidence', []))} 条证据）",
                data=report.model_dump(mode="json"),
            ))

        # If QA passes, move to export; if blocked, stay at opportunity
        next_g = ResearchGate.EXPORT.value if not qa_issues else ResearchGate.KNOWLEDGE_MAP.value
        return {"current_gate": next_g, "qa_issues": qa_issues, "qa_report": report.model_dump(mode="json")}

    async def export_gate(state: WorkflowState) -> dict[str, Any]:
        await _emit(emitter, RunEvent(
            event_type="node_started", gate="export", agent="Export Writer", message="正在导出知识库",
        ))
        await _emit(emitter, RunEvent(
            event_type="node_progress", gate="export", step="write", agent="Export Writer",
            message=f"已生成 {len(state.get('artifacts', []))} 个产物，{len(state.get('evidence', []))} 条证据",
        ))
        await _emit(emitter, RunEvent(
            event_type="node_completed", gate="export", agent="RAG Indexer", message="研究完成，已预留项目检索索引",
        ))
        return {"current_gate": ResearchGate.EXPORT.value}

    return {
        "scope_gate": scope_gate,
        "supervisor_plan_gate": supervisor_plan_gate,
        "source_strategy_gate": source_strategy_gate,
        "evidence_gate": evidence_gate,
        "evidence_ledger_gate": evidence_ledger_gate,
        "claim_extractor_gate": claim_extractor_gate,
        "counterevidence_gate": counterevidence_gate,
        "research_frame_gate": research_frame_gate,
        "market_gate": market_gate,
        "player_gate": player_gate,
        "transaction_gate": transaction_gate,
        "synthesis_gate": synthesis_gate,
        "knowledge_map_gate": knowledge_map_gate,
        "qa_critic_gate": qa_critic_gate,
        "export_gate": export_gate,
    }


# ── Graph construction ────────────────────────────────────────

def _route_after_qa(state: WorkflowState) -> str:
    if state.get("qa_issues"):
        return "blocked"
    return "export_gate"


def build_graph(
    llm_provider: LLMProvider | None = None,
    search_provider: SearchProvider | None = None,
    content_extraction_provider: ContentExtractionProvider | None = None,
    emitter: EventEmitter | None = None,
):
    """Build the LangGraph StateGraph with typed state and explicit edges."""
    nodes = make_nodes(llm_provider, search_provider, content_extraction_provider, emitter)

    graph = StateGraph(WorkflowState)

    # Add nodes
    graph.add_node("scope_gate", nodes["scope_gate"])
    graph.add_node("supervisor_plan_gate", nodes["supervisor_plan_gate"])
    graph.add_node("source_strategy_gate", nodes["source_strategy_gate"])
    graph.add_node("evidence_gate", nodes["evidence_gate"])
    graph.add_node("claim_extractor_gate", nodes["claim_extractor_gate"])
    graph.add_node("counterevidence_gate", nodes["counterevidence_gate"])
    graph.add_node("evidence_ledger_gate", nodes["evidence_ledger_gate"])
    graph.add_node("research_frame_gate", nodes["research_frame_gate"])
    graph.add_node("market_gate", nodes["market_gate"])
    graph.add_node("player_gate", nodes["player_gate"])
    graph.add_node("transaction_gate", nodes["transaction_gate"])
    graph.add_node("synthesis_gate", nodes["synthesis_gate"])
    graph.add_node("knowledge_map_gate", nodes["knowledge_map_gate"])
    graph.add_node("qa_critic_gate", nodes["qa_critic_gate"])
    graph.add_node("export_gate", nodes["export_gate"])

    # Set entry point
    graph.set_entry_point("scope_gate")

    # Add edges
    graph.add_edge("scope_gate", "supervisor_plan_gate")
    graph.add_edge("supervisor_plan_gate", "source_strategy_gate")
    graph.add_edge("source_strategy_gate", "evidence_gate")
    graph.add_edge("evidence_gate", "claim_extractor_gate")
    graph.add_edge("claim_extractor_gate", "counterevidence_gate")
    graph.add_edge("counterevidence_gate", "evidence_ledger_gate")
    graph.add_edge("evidence_ledger_gate", "research_frame_gate")
    graph.add_edge("research_frame_gate", "market_gate")
    graph.add_edge("market_gate", "player_gate")
    graph.add_edge("player_gate", "transaction_gate")
    graph.add_edge("transaction_gate", "synthesis_gate")
    graph.add_edge("synthesis_gate", "knowledge_map_gate")
    graph.add_edge("knowledge_map_gate", "qa_critic_gate")

    # Conditional edge after QA
    graph.add_conditional_edges(
        "qa_critic_gate",
        _route_after_qa,
        {"export_gate": "export_gate", "blocked": END},
    )

    graph.add_edge("export_gate", END)

    return graph.compile()


# ── Public API ─────────────────────────────────────────────────


def _initial_state(project: ResearchProject) -> WorkflowState:
    return {
        "project": project.model_dump(mode="json"),
        "project_id": project.id,
        "current_gate": ResearchGate.SCOPE.value,
        "evidence": [],
        "artifacts": [],
        "supervisor_plan": None,
        "coverage_checklist": {},
        "qa_issues": [],
        "qa_report": None,
        "user_guidance": None,
        "user_evidence_items": [],
        "seed_evidence_items": [],
        "assistant_brief": None,
    }


def _state_to_json(state: WorkflowState) -> str:
    return json.dumps(state, ensure_ascii=False, default=str)


def _state_from_json(data: str) -> WorkflowState:
    return json.loads(data)


def _to_research_state(raw: WorkflowState) -> ResearchState:
    return ResearchState(
        project_id=raw["project_id"],
        current_gate=ResearchGate(raw.get("current_gate", ResearchGate.EXPORT.value)),
        evidence=[EvidenceItem(**item) for item in raw.get("evidence", [])],
        artifacts=[Artifact(**item) for item in raw.get("artifacts", [])],
        supervisor_plan=SupervisorPlan(**raw["supervisor_plan"]) if raw.get("supervisor_plan") else None,
        coverage_checklist=raw.get("coverage_checklist", {}),
        qa_issues=raw.get("qa_issues", []),
        qa_report=QAReport(**raw["qa_report"]) if raw.get("qa_report") else None,
    )


async def run_research_workflow(
    project: ResearchProject,
    search_provider: SearchProvider | None = None,
    content_extraction_provider: ContentExtractionProvider | None = None,
    llm_provider: LLMProvider | None = None,
    emitter: EventEmitter | None = None,
    user_guidance: str | None = None,
    user_evidence_items: list[dict[str, Any]] | None = None,
    seed_evidence_items: list[dict[str, Any]] | None = None,
    assistant_brief: str | None = None,
) -> ResearchState:
    """Run all gates without pausing (for tests and auto-run mode)."""
    state = _initial_state(project)
    state["user_guidance"] = user_guidance
    state["user_evidence_items"] = user_evidence_items or []
    state["seed_evidence_items"] = seed_evidence_items or []
    state["assistant_brief"] = assistant_brief

    graph = build_graph(llm_provider, search_provider, content_extraction_provider, emitter)
    raw_state = await graph.ainvoke(state)

    return _to_research_state(raw_state)


async def run_workflow_until_pause(
    project: ResearchProject,
    search_provider: SearchProvider | None = None,
    content_extraction_provider: ContentExtractionProvider | None = None,
    llm_provider: LLMProvider | None = None,
    emitter: EventEmitter | None = None,
    state: WorkflowState | None = None,
    user_guidance: str | None = None,
    user_evidence_items: list[dict[str, Any]] | None = None,
    seed_evidence_items: list[dict[str, Any]] | None = None,
    assistant_brief: str | None = None,
    auto_run: bool = False,
) -> tuple[WorkflowState, str | None, bool]:
    """Run gates sequentially until one requires human review or all complete.

    Returns (state, paused_gate, completed).
    """
    if state is None:
        state = _initial_state(project)
    if user_guidance:
        state["user_guidance"] = user_guidance
    if user_evidence_items:
        state["user_evidence_items"] = user_evidence_items
    if seed_evidence_items:
        state["seed_evidence_items"] = _merge_evidence_items(
            state.get("seed_evidence_items", []),
            seed_evidence_items,
        )
    if assistant_brief:
        state["assistant_brief"] = assistant_brief
    if state.get("supervisor_plan") and (assistant_brief or user_evidence_items or user_guidance):
        state["supervisor_plan"] = build_supervisor_plan(
            project,
            user_guidance=state.get("user_guidance"),
            has_assistant_brief=bool(state.get("assistant_brief")),
            has_user_materials=bool(state.get("user_evidence_items")),
        ).model_dump(mode="json")

    nodes = make_nodes(llm_provider, search_provider, content_extraction_provider, emitter)
    current = state.get("current_gate", GATE_ORDER[0])

    while current:
        fn = nodes.get(current) or nodes.get(f"{current}_gate")
        if fn:
            update = await fn(state)
            state.update(update)
            state["current_gate"] = current

        # QA blocks further gates
        if current == "qa_critic" and state.get("qa_issues"):
            state["current_gate"] = ResearchGate.KNOWLEDGE_MAP.value
            return state, None, True

        # Check pause
        if not auto_run and current in HUMAN_REVIEW_GATES:
            nxt = next_gate(current)
            state["current_gate"] = nxt or current
            return state, current, False

        # Next gate
        nxt = next_gate(current)
        if nxt:
            state["current_gate"] = nxt
            current = nxt
        else:
            return state, None, True

    return state, None, True
