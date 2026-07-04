"""Simplified runnable V1 knowledge-system pipeline."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.app.graph.workflow import search_constraints_for_policy
from backend.app.providers.interfaces import (
    ChatMessage,
    ContentExtractionProvider,
    LLMProvider,
    SearchProvider,
    SearchQuery,
    SearchResult,
)
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ClaimStrength,
    ClaimType,
    EvidenceClaim,
    EvidenceItem,
    ResearchProject,
    RunEvent,
    SourceChannel,
    SourcePolicy,
    SourceQuality,
    VerificationStatus,
)
from backend.app.storage.sqlite import SQLiteRepository


class V1KnowledgeContent(BaseModel):
    domain_overview: str = ""
    learning_path: str | list[Any] = ""
    core_concepts: str = ""
    player_tool_map: str = ""
    trend_evidence: str = ""
    problem_opportunity_map: str = ""
    unresolved_questions: str = ""
    title: str | None = None
    content: str | None = None
    sections: list[Any] = Field(default_factory=list)


class DomainConcept(BaseModel):
    name: str
    definition: str
    why_it_matters: str
    related: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class DomainArchitecture(BaseModel):
    name: str
    summary: str
    use_cases: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class DomainTool(BaseModel):
    name: str
    category: str
    use_case: str
    tradeoffs: str
    evidence_ids: list[str] = Field(default_factory=list)


class DomainKnowledgeBase(BaseModel):
    overview: str = ""
    concepts: list[DomainConcept] = Field(default_factory=list)
    architectures: list[DomainArchitecture] = Field(default_factory=list)
    tools: list[DomainTool] = Field(default_factory=list)
    trends: list[str] = Field(default_factory=list)
    learning_path: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ArtifactExpansionReview(BaseModel):
    needs_expansion: bool = False
    detail_score: int = Field(default=7, ge=1, le=10)
    missing_angles: list[str] = Field(default_factory=list)
    expansion_brief: str = ""
    quality_notes: str = ""


class DocumentSourceSummary(BaseModel):
    document_id: str
    channel: str
    file_name: str | None = None
    char_count: int = 0
    segment_count: int = 0
    citation_count: int = 0
    summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class SearchIntent(BaseModel):
    intent: str
    query: str
    reason: str
    coverage_dimensions: list[str] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)


class SearchPlan(BaseModel):
    objective: str = ""
    intents: list[SearchIntent] = Field(default_factory=list)


class ToolCallResult(BaseModel):
    tool: str = "search"
    intent: str
    query: str
    raw_result_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    rejected_reasons: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class CoverageReport(BaseModel):
    status: str = "needs_more_sources"
    can_continue: bool = False
    coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)
    covered_dimensions: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    next_search_intents: list[SearchIntent] = Field(default_factory=list)
    reason: str = ""
    block_reason: str | None = None


class MasterAgentDecision(BaseModel):
    action: str = "search_again"
    reason: str = ""
    coverage_report: CoverageReport


class RunWorkingMemory(BaseModel):
    objective: str
    source_policy: str
    document_sources: list[DocumentSourceSummary] = Field(default_factory=list)
    search_round: int = 0
    attempted_queries: list[str] = Field(default_factory=list)
    tool_results: list[ToolCallResult] = Field(default_factory=list)
    coverage_reports: list[CoverageReport] = Field(default_factory=list)
    decisions: list[MasterAgentDecision] = Field(default_factory=list)


_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\([^)]+\)")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)]\([^)]+\)")
_RAW_URL_RE = re.compile(r"https?://\S+")
_WHITESPACE_RE = re.compile(r"\s+")
_V1_SNIPPET_MAX_CHARS = 420
_V1_TARGET_EVIDENCE_COUNT = 10
_V1_MIN_ACCEPTABLE_EVIDENCE_COUNT = 8
_V1_MASTER_MAX_SEARCH_ROUNDS = 3
_V1_MASTER_MAX_INTENTS_PER_ROUND = 4
_V1_ZERO_EVIDENCE_BLOCK_MESSAGE = (
    "资料收集后仍没有可用证据，已停止生成知识库。请检查搜索配置、换一个更明确的主题、"
    "切换信源策略，或上传外部报告/用户材料后重新运行。"
)
_V1_BLOCKED_DOMAINS = (
    "github.com",
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "tiktok.com",
)
_V1_ATTACHMENT_EXTENSIONS = (".pdf", ".xls", ".xlsx", ".ppt", ".pptx", ".doc", ".docx")
_V1_LOW_SIGNAL_TITLE_MARKERS = (
    "[pdf]",
    "[xls]",
    "[xlsx]",
    "instagram",
    "youtube",
    "議程表",
    "agenda",
)
_CHINESE_TOPIC_MARKERS = (
    "大模型",
    "智能体",
    "agent",
    "开发",
    "就业",
    "岗位",
    "职业",
    "架构",
    "工具",
    "框架",
    "应用",
    "高考",
    "教育",
    "培训",
    "在线教育",
    "线上培训",
    "教培",
    "升学",
    "课程",
    "学习",
    "市场",
    "行业",
)
_GENERIC_SHORT_TOPIC_TOKENS = {
    "线上",
    "在线",
    "行业",
    "市场",
    "服务",
    "平台",
    "工具",
    "应用",
    "发展",
    "趋势",
}

_SEARCH_SNIPPET_NOISE_MARKERS = (
    "skip to content",
    "sign in",
    "sign up",
    "navigation menu",
    "search code",
    "repositories",
    "users, issues",
    "pull requests",
    "you signed in with another tab",
    "reload to refresh your session",
    "you switched accounts",
    "dismiss alert",
    "github skills",
    "notifications",
)


async def run_v1_knowledge_pipeline(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    search_provider: SearchProvider | None,
    content_extraction_provider: ContentExtractionProvider | None = None,
    llm_provider: LLMProvider | None,
    emit: Callable[[RunEvent], Awaitable[None]] | None = None,
) -> list[Artifact]:
    """Run the product-facing V1 path and persist evidence plus artifacts."""

    async def emit_event(event: RunEvent) -> None:
        if emit is not None:
            await emit(event)

    evidence = list(repository.list_evidence(project.id))
    memory = RunWorkingMemory(
        objective=f"为“{project.domain}”构建可持续补充的 Obsidian 领域知识库",
        source_policy=project.source_policy.value,
    )

    await emit_event(RunEvent(
        event_type="node_started",
        gate="master_agent",
        agent="Master Agent",
        message="主管节点开始理解任务、检查上传材料和已有证据",
        progress_current=1,
        progress_total=4,
    ))

    memory.document_sources = await _ingest_project_documents(
        project=project,
        repository=repository,
        evidence=evidence,
        emit_event=emit_event,
    )

    await emit_event(RunEvent(
        event_type="node_started",
        gate="source_collection",
        agent="Search Scout",
        message="Master Agent 开始按调研意图调用搜索工具",
        progress_current=1,
        progress_total=_V1_MASTER_MAX_SEARCH_ROUNDS,
        data={"document_sources": [item.model_dump(mode="json") for item in memory.document_sources]},
    ))

    if project.source_policy != SourcePolicy.USER_MATERIALS_ONLY and search_provider is not None:
        allowed_domains, blocked_domains = search_constraints_for_policy(
            {
                "market_scope": project.market_scope.value,
                "source_policy": project.source_policy.value,
            },
            verification=project.source_policy == SourcePolicy.RELIABLE_ONLY,
        )
        v1_blocked_domains = list(dict.fromkeys(blocked_domains + list(_V1_BLOCKED_DOMAINS)))

        for round_index in range(1, _V1_MASTER_MAX_SEARCH_ROUNDS + 1):
            memory.search_round = round_index
            search_plan = await _build_master_search_plan(
                project=project,
                evidence=evidence,
                memory=memory,
                llm_provider=llm_provider,
                round_index=round_index,
                emit_event=emit_event,
            )
            tool_results = await _execute_search_intents(
                project=project,
                repository=repository,
                evidence=evidence,
                search_provider=search_provider,
                intents=search_plan.intents,
                allowed_domains=allowed_domains if round_index == 1 else [],
                blocked_domains=v1_blocked_domains,
                memory=memory,
                emit_event=emit_event,
            )
            memory.tool_results.extend(tool_results)
            if (
                sum(item.accepted_count for item in tool_results) == 0
                and project.source_policy == SourcePolicy.RELIABLE_FIRST
                and round_index == 1
                and allowed_domains
            ):
                await emit_event(RunEvent(
                    event_type="node_degraded",
                    gate="source_collection",
                    agent="Search Scout",
                    message="可靠优先来源暂未命中，Master Agent 已降级补充开放网络搜索",
                    progress_current=round_index,
                    progress_total=_V1_MASTER_MAX_SEARCH_ROUNDS,
                    severity="warning",
                ))
                open_web_results = await _execute_search_intents(
                    project=project,
                    repository=repository,
                    evidence=evidence,
                    search_provider=search_provider,
                    intents=search_plan.intents,
                    allowed_domains=[],
                    blocked_domains=v1_blocked_domains,
                    memory=memory,
                    emit_event=emit_event,
                )
                memory.tool_results.extend(open_web_results)

            coverage = await _evaluate_coverage_with_master_agent(
                project=project,
                evidence=evidence,
                memory=memory,
                llm_provider=llm_provider,
                emit_event=emit_event,
            )
            memory.coverage_reports.append(coverage)
            decision = _decision_from_coverage(coverage)
            memory.decisions.append(decision)
            decision_event: dict[str, Any] = {
                "event_type": "node_progress" if decision.action in {"continue", "degrade"} else "node_degraded",
                "gate": "master_agent",
                "agent": "Master Agent",
                "message": f"主管判断：{decision.reason}",
                "progress_current": round_index,
                "progress_total": _V1_MASTER_MAX_SEARCH_ROUNDS,
                "data": decision.model_dump(mode="json"),
            }
            if decision.action in {"search_again", "degrade"}:
                decision_event["severity"] = "warning"
            await emit_event(RunEvent(**decision_event))
            if decision.action in {"continue", "degrade"}:
                break
            if decision.action == "block":
                await _emit_zero_or_low_evidence_block(
                    project=project,
                    evidence=evidence,
                    search_provider=search_provider,
                    coverage=coverage,
                    emit_event=emit_event,
                )
            if round_index == _V1_MASTER_MAX_SEARCH_ROUNDS:
                if coverage.can_continue and evidence:
                    break
                await _emit_zero_or_low_evidence_block(
                    project=project,
                    evidence=evidence,
                    search_provider=search_provider,
                    coverage=coverage,
                    emit_event=emit_event,
                )
    else:
        coverage = await _evaluate_coverage_with_master_agent(
            project=project,
            evidence=evidence,
            memory=memory,
            llm_provider=llm_provider,
            emit_event=emit_event,
        )
        memory.coverage_reports.append(coverage)
        decision = _decision_from_coverage(coverage)
        memory.decisions.append(decision)
        decision_event = {
            "event_type": "node_progress" if decision.action in {"continue", "degrade"} else "node_degraded",
            "gate": "master_agent",
            "agent": "Master Agent",
            "message": f"主管判断：{decision.reason}",
            "progress_current": 1,
            "progress_total": 1,
            "data": decision.model_dump(mode="json"),
        }
        if decision.action != "continue":
            decision_event["severity"] = "warning"
        await emit_event(RunEvent(**decision_event))

    if len(evidence) == 0:
        await emit_event(RunEvent(
            event_type="node_blocked",
            gate="source_collection",
            agent="Search Scout",
            message=_V1_ZERO_EVIDENCE_BLOCK_MESSAGE,
            progress_current=0,
            progress_total=_V1_TARGET_EVIDENCE_COUNT,
            severity="error",
            data={
                "status": "blocked",
                "reason": "zero_evidence",
                "source_policy": project.source_policy.value,
                "search_configured": search_provider is not None,
            },
        ))
        raise RuntimeError(_V1_ZERO_EVIDENCE_BLOCK_MESSAGE)

    final_coverage = memory.coverage_reports[-1] if memory.coverage_reports else _fallback_coverage_report(project, evidence, memory)
    if not final_coverage.can_continue and final_coverage.status == "blocked":
        await _emit_zero_or_low_evidence_block(
            project=project,
            evidence=evidence,
            search_provider=search_provider,
            coverage=final_coverage,
            emit_event=emit_event,
        )
    if not final_coverage.can_continue:
        await emit_event(RunEvent(
            event_type="node_degraded",
            gate="coverage_evaluation",
            agent="Master Agent",
            message="主管节点认为资料仍不完整，本轮只能降级生成待补证知识库",
            progress_current=len(evidence),
            progress_total=_V1_TARGET_EVIDENCE_COUNT,
            severity="warning",
            data=final_coverage.model_dump(mode="json"),
        ))

    await emit_event(RunEvent(
        event_type="node_completed",
        gate="source_collection",
        agent="Search Scout",
        message=f"资料收集完成，当前证据 {len(evidence)} 条；主管覆盖判断：{final_coverage.status}",
        progress_current=1,
        progress_total=3,
        data=final_coverage.model_dump(mode="json"),
    ))
    await emit_event(RunEvent(
        event_type="node_started",
        gate="knowledge_structuring",
        agent="Knowledge Builder",
        message="开始生成 V1 知识系统",
        progress_current=2,
        progress_total=3,
    ))
    await emit_event(RunEvent(
        event_type="node_progress",
        gate="knowledge_structuring",
        agent="Knowledge Builder",
        message="正在抽取概念、架构、工具、趋势和学习路径",
        progress_current=1,
        progress_total=2,
    ))

    database = await _build_knowledge_database(
        project=project,
        evidence=evidence,
        llm_provider=llm_provider,
        emit_event=emit_event,
    )
    await emit_event(RunEvent(
        event_type="node_progress",
        gate="knowledge_structuring",
        agent="Knowledge Builder",
        message=(
            f"领域数据库生成完成：{len(database.concepts)} 个概念、"
            f"{len(database.architectures)} 个架构、{len(database.tools)} 个工具"
        ),
        progress_current=2,
        progress_total=2,
    ))
    source_evidence_ids = [item.id for item in evidence]
    artifacts = await _build_artifacts(
        project,
        database,
        source_evidence_ids,
        llm_provider=llm_provider,
        emit_event=emit_event,
    )
    for artifact in artifacts:
        repository.add_artifact(artifact)

    await emit_event(RunEvent(
        event_type="node_completed",
        gate="knowledge_structuring",
        agent="Knowledge Builder",
        message="V1 知识系统生成完成",
        progress_current=2,
        progress_total=3,
    ))
    await emit_event(RunEvent(
        event_type="node_completed",
        gate="obsidian_export",
        agent="Export Writer",
        message="V1 Markdown 产物已写入项目",
        progress_current=3,
        progress_total=3,
    ))
    return artifacts


async def _persist_search_results(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    evidence: list[EvidenceItem],
    results: list[SearchResult],
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> list[str]:
    added_ids: list[str] = []
    seen_urls = {item.source_url for item in evidence if item.source_url}
    for result in results:
        if result.url in seen_urls:
            continue
        item = _search_result_to_evidence(project, result, len(evidence) + 1)
        repository.add_evidence(item)
        evidence.append(item)
        added_ids.append(item.id)
        seen_urls.add(result.url)
        await emit_event(RunEvent(
            event_type="evidence_collected",
            gate="source_collection",
            agent="Search Scout",
            message=f"已记录来源：{result.title}",
            data={"evidence_id": item.id, "url": result.url},
        ))
    return added_ids


async def _ingest_project_documents(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    evidence: list[EvidenceItem],
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> list[DocumentSourceSummary]:
    list_documents = getattr(repository, "list_documents", None)
    if list_documents is None:
        return []
    documents = list_documents(project.id)
    if not documents:
        return []

    await emit_event(RunEvent(
        event_type="node_started",
        gate="external_report_intake",
        agent="External Report Agent",
        message=f"开始读取上传材料：{len(documents)} 个文档",
        progress_current=1,
        progress_total=max(1, len(documents)),
    ))

    existing_ids = {item.id for item in evidence}
    summaries: list[DocumentSourceSummary] = []
    for index, document in enumerate(documents, start=1):
        summary = DocumentSourceSummary(
            document_id=document.id,
            channel=document.channel,
            file_name=document.file_name,
            char_count=document.char_count,
            segment_count=document.segment_count,
            citation_count=document.citation_count,
            summary=_truncate_text(document.content, 360),
        )
        doc_evidence = _document_to_v1_evidence(project, document, len(evidence) + 1)
        if doc_evidence.id not in existing_ids:
            repository.add_evidence(doc_evidence)
            evidence.append(doc_evidence)
            existing_ids.add(doc_evidence.id)
            summary.evidence_ids.append(doc_evidence.id)

        list_citations = getattr(repository, "list_document_citations", None)
        list_segments = getattr(repository, "list_document_segments", None)
        citations = list_citations(document.id) if list_citations is not None else []
        segments = list_segments(document.id) if list_segments is not None else []
        for citation in citations[:12]:
            citation_evidence = _document_citation_to_v1_evidence(
                project=project,
                document=document,
                citation=citation,
                segment_text=_segment_text_for_citation(citation, segments),
                index=len(evidence) + 1,
            )
            if citation_evidence.id in existing_ids:
                continue
            repository.add_evidence(citation_evidence)
            evidence.append(citation_evidence)
            existing_ids.add(citation_evidence.id)
            summary.evidence_ids.append(citation_evidence.id)

        summaries.append(summary)
        await emit_event(RunEvent(
            event_type="evidence_collected",
            gate="external_report_intake",
            agent="External Report Agent",
            message=(
                f"已采纳上传材料：{document.file_name or document.id}，"
                f"提取引用 {document.citation_count} 条"
            ),
            progress_current=index,
            progress_total=len(documents),
            data=summary.model_dump(mode="json"),
        ))

    await emit_event(RunEvent(
        event_type="node_completed",
        gate="external_report_intake",
        agent="External Report Agent",
        message=f"上传材料读取完成：{len(summaries)} 个文档，已进入 Master Agent 上下文",
        progress_current=len(summaries),
        progress_total=max(1, len(documents)),
        data={"documents": [item.model_dump(mode="json") for item in summaries]},
    ))
    return summaries


def _document_to_v1_evidence(project: ResearchProject, document: Any, index: int) -> EvidenceItem:
    channel = SourceChannel.ASSISTANT_BRIEF if document.channel == "assistant_brief" else SourceChannel.USER_UPLOAD
    source_type = "assistant_brief" if document.channel == "assistant_brief" else "user_material"
    snippet = _truncate_text(document.content, _V1_SNIPPET_MAX_CHARS)
    evidence_id = f"EV-DOC-{document.id}"
    return EvidenceItem(
        id=evidence_id,
        project_id=project.id,
        source_title=document.file_name or f"上传材料 {index}",
        source_type=source_type,
        source_channel=channel,
        source_policy=project.source_policy.value,
        raw_excerpt=snippet,
        snippet=snippet,
        summary=snippet,
        claims=[
            EvidenceClaim(
                claim_id=f"{evidence_id}-CLAIM-1",
                text=snippet,
                support_level=0.45,
                requires_verification=True,
                verification_status=VerificationStatus.UNVERIFIED,
                evidence_ids=[evidence_id],
                notes="用户上传或外部 AI 报告材料，作为低可信研究输入进入 Master Agent 上下文。",
            )
        ],
        source_quality=SourceQuality.LOW if document.channel == "assistant_brief" else SourceQuality.MEDIUM,
        claim_strength=ClaimStrength.OPINION,
        bias_risk="uploaded_external_report" if document.channel == "assistant_brief" else "user_material",
        needs_counterevidence=document.channel == "assistant_brief",
        collected_by="v1_external_report_intake",
        confidence=0.45 if document.channel == "assistant_brief" else 0.55,
        verification_status=VerificationStatus.UNVERIFIED,
    )


def _document_citation_to_v1_evidence(
    *,
    project: ResearchProject,
    document: Any,
    citation: Any,
    segment_text: str,
    index: int,
) -> EvidenceItem:
    evidence_id = f"EV-DOC-CIT-{citation.id}"
    title = citation.source_title or citation.source_url or citation.raw_reference or f"上传材料引用 {index}"
    snippet = _truncate_text(segment_text or f"上传材料引用来源：{citation.raw_reference}", _V1_SNIPPET_MAX_CHARS)
    return EvidenceItem(
        id=evidence_id,
        project_id=project.id,
        source_title=title,
        source_url=citation.source_url,
        source_type="web",
        source_channel=SourceChannel.ASSISTANT_BRIEF if document.channel == "assistant_brief" else SourceChannel.MANUAL_LINK,
        source_policy=project.source_policy.value,
        raw_excerpt=snippet,
        snippet=snippet,
        summary=snippet,
        claims=[
            EvidenceClaim(
                claim_id=f"{evidence_id}-CLAIM-1",
                text=snippet,
                support_level=0.5,
                requires_verification=True,
                verification_status=VerificationStatus.PARTIALLY_VERIFIED,
                evidence_ids=[evidence_id],
                notes="从上传材料中提取的引用链接，需继续复核原网页。",
            )
        ],
        source_quality=SourceQuality.MEDIUM,
        claim_strength=ClaimStrength.OPINION,
        bias_risk="citation_from_uploaded_report",
        needs_counterevidence=True,
        collected_by="v1_external_report_citation",
        confidence=0.5,
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
    )


def _segment_text_for_citation(citation: Any, segments: list[Any]) -> str:
    segment_ids = set(getattr(citation, "referenced_segment_ids", []) or [])
    for segment in segments:
        if segment.id in segment_ids:
            return segment.text
    return ""


async def _build_master_search_plan(
    *,
    project: ResearchProject,
    evidence: list[EvidenceItem],
    memory: RunWorkingMemory,
    llm_provider: LLMProvider | None,
    round_index: int,
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> SearchPlan:
    fallback = _fallback_search_plan(project=project, memory=memory, round_index=round_index)
    plan = fallback
    if llm_provider is not None:
        prompt = (
            "你是 SectorBreaker 的 Master Agent。请根据研究目标、上传材料、已有证据和覆盖缺口，"
            "生成下一轮搜索计划。搜索必须围绕研究意图展开，不要机械拆词。"
            "最多给出 4 个 SearchIntent，每个 query 应该可直接交给搜索 API。\n\n"
            f"研究目标：{memory.objective}\n"
            f"领域：{project.domain}\n"
            f"市场范围：{project.market_scope.value}\n"
            f"信源策略：{project.source_policy.value}\n"
            f"已搜索 query：{memory.attempted_queries[-12:]}\n"
            f"上传材料：{[item.model_dump(mode='json') for item in memory.document_sources]}\n"
            f"当前证据摘要：{_evidence_brief(evidence)}\n"
            f"上一轮覆盖判断：{memory.coverage_reports[-1].model_dump(mode='json') if memory.coverage_reports else '无'}"
        )
        try:
            generated = await llm_provider.complete_structured([ChatMessage(role="user", content=prompt)], SearchPlan)
            if isinstance(generated, SearchPlan) and generated.intents:
                plan = generated
        except Exception as exc:
            await emit_event(RunEvent(
                event_type="node_degraded",
                gate="master_agent",
                agent="Master Agent",
                message=f"LLM 搜索计划生成失败，已使用内置多意图计划：{type(exc).__name__}",
                progress_current=round_index,
                progress_total=_V1_MASTER_MAX_SEARCH_ROUNDS,
                severity="warning",
            ))

    plan = SearchPlan(
        objective=plan.objective or fallback.objective,
        intents=_dedupe_search_intents(plan.intents, memory.attempted_queries)[:_V1_MASTER_MAX_INTENTS_PER_ROUND]
        or fallback.intents[:_V1_MASTER_MAX_INTENTS_PER_ROUND],
    )
    await emit_event(RunEvent(
        event_type="node_progress",
        gate="master_agent",
        agent="Master Agent",
        message=(
            f"第 {round_index} 轮搜索计划："
            + "；".join(f"{item.intent} -> {item.query}" for item in plan.intents)
        ),
        progress_current=round_index,
        progress_total=_V1_MASTER_MAX_SEARCH_ROUNDS,
        data=plan.model_dump(mode="json"),
    ))
    return plan


def _fallback_search_plan(
    *,
    project: ResearchProject,
    memory: RunWorkingMemory,
    round_index: int,
) -> SearchPlan:
    topic = project.domain.strip()
    latest_missing = memory.coverage_reports[-1].missing_dimensions if memory.coverage_reports else []
    dimensions = latest_missing or [
        "concept_boundary",
        "current_state",
        "trends_reports",
        "policy_risk",
        "cases_players",
        "user_demand",
    ]
    intent_by_dimension = {
        "concept_boundary": SearchIntent(
            intent="建立领域边界与核心术语",
            query=f"{topic} 核心概念 术语 入门 指南 领域边界",
            reason="先确认这个领域到底包含什么、不包含什么，避免后续建库跑偏。",
            coverage_dimensions=["concept_boundary"],
            expected_sources=["百科/教程", "官方说明", "研究综述"],
        ),
        "current_state": SearchIntent(
            intent="了解现状与市场/应用进展",
            query=f"{topic} 现状 行业趋势 市场规模 应用进展 2026",
            reason="补充当前发展阶段、需求变化和关键事实背景。",
            coverage_dimensions=["current_state"],
            expected_sources=["研究报告", "行业文章", "公开数据"],
        ),
        "trends_reports": SearchIntent(
            intent="寻找近期趋势和研究报告",
            query=f"{topic} 趋势 研究报告 数据报告 2025 2026",
            reason="为趋势判断寻找近期来源，而不是只依赖泛泛介绍。",
            coverage_dimensions=["trends_reports"],
            expected_sources=["报告", "数据文章", "机构分析"],
        ),
        "policy_risk": SearchIntent(
            intent="检查政策监管与风险约束",
            query=f"{topic} 政策 监管 风险 合规 问题 2026",
            reason="建立风险和边界意识，避免知识库只写机会不写约束。",
            coverage_dimensions=["policy_risk"],
            expected_sources=["政府/监管", "标准", "法律/合规解读"],
        ),
        "cases_players": SearchIntent(
            intent="寻找案例、玩家和工具/平台",
            query=f"{topic} 案例 公司 平台 工具 主要玩家 实践",
            reason="用案例和参与者把抽象概念落到真实对象。",
            coverage_dimensions=["cases_players"],
            expected_sources=["公司官网", "案例", "产品/工具文档"],
        ),
        "user_demand": SearchIntent(
            intent="理解用户需求、学习路径与痛点",
            query=f"{topic} 用户需求 痛点 学习路径 常见问题 经验",
            reason="SectorBreaker 的目标是帮助入局，需要知道新用户该学什么、会卡在哪里。",
            coverage_dimensions=["user_demand"],
            expected_sources=["问答/社区", "教程", "用户反馈"],
        ),
        "source_quality": SearchIntent(
            intent="补充权威和可复核来源",
            query=_build_v1_supplemental_search_query(topic),
            reason="当前来源可信度或数量偏薄，需要补充可回链资料。",
            coverage_dimensions=["source_quality"],
            expected_sources=["官方", "机构报告", "公开数据库"],
        ),
    }

    selected: list[SearchIntent] = []
    for dimension in dimensions:
        normalized = _normalize_dimension_id(dimension)
        selected.append(intent_by_dimension.get(normalized, intent_by_dimension["source_quality"]))
    if round_index == 1 and not selected:
        selected = list(intent_by_dimension.values())[:_V1_MASTER_MAX_INTENTS_PER_ROUND]
    if round_index >= 2:
        selected.append(intent_by_dimension["source_quality"])
    return SearchPlan(
        objective=f"围绕“{topic}”补足领域建库所需的概念、现状、趋势、风险、案例和需求证据",
        intents=_dedupe_search_intents(selected, memory.attempted_queries)[:_V1_MASTER_MAX_INTENTS_PER_ROUND]
        or list(intent_by_dimension.values())[:_V1_MASTER_MAX_INTENTS_PER_ROUND],
    )


def _dedupe_search_intents(intents: list[SearchIntent], attempted_queries: list[str]) -> list[SearchIntent]:
    attempted = {query.strip().lower() for query in attempted_queries}
    seen: set[str] = set()
    deduped: list[SearchIntent] = []
    for intent in intents:
        query = _truncate_text(intent.query, 160)
        key = query.lower()
        if not query or key in seen or key in attempted:
            continue
        seen.add(key)
        deduped.append(intent.model_copy(update={"query": query}))
    return deduped


async def _execute_search_intents(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    evidence: list[EvidenceItem],
    search_provider: SearchProvider,
    intents: list[SearchIntent],
    allowed_domains: list[str],
    blocked_domains: list[str],
    memory: RunWorkingMemory,
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> list[ToolCallResult]:
    tool_results: list[ToolCallResult] = []
    for index, intent in enumerate(intents[:_V1_MASTER_MAX_INTENTS_PER_ROUND], start=1):
        memory.attempted_queries.append(intent.query)
        await emit_event(RunEvent(
            event_type="node_progress",
            gate="source_collection",
            agent="Search Scout",
            message=f"正在搜索：{intent.intent}（{intent.query}）",
            progress_current=index,
            progress_total=max(1, len(intents[:_V1_MASTER_MAX_INTENTS_PER_ROUND])),
            data=intent.model_dump(mode="json"),
        ))
        try:
            raw_results = await search_provider.search(SearchQuery(
                query=intent.query,
                market_scope=project.market_scope.value,
                max_results=6,
                allowed_domains=allowed_domains,
                blocked_domains=blocked_domains,
            ))
        except Exception as exc:
            result = ToolCallResult(
                intent=intent.intent,
                query=intent.query,
                rejected_reasons=[f"search_error:{type(exc).__name__}"],
            )
            tool_results.append(result)
            await emit_event(RunEvent(
                event_type="node_degraded",
                gate="source_collection",
                agent="Search Scout",
                message=f"搜索工具调用失败：{intent.intent}，{type(exc).__name__}",
                progress_current=index,
                progress_total=max(1, len(intents)),
                severity="warning",
                data=result.model_dump(mode="json"),
            ))
            continue

        accepted = _filter_v1_search_results(raw_results, project=project)
        added_ids = await _persist_search_results(
            project=project,
            repository=repository,
            evidence=evidence,
            results=accepted,
            emit_event=emit_event,
        )
        rejected_count = max(0, len(raw_results) - len(accepted))
        result = ToolCallResult(
            intent=intent.intent,
            query=intent.query,
            raw_result_count=len(raw_results),
            accepted_count=len(added_ids),
            rejected_count=rejected_count,
            rejected_reasons=_search_rejection_summary(raw_results, accepted, project),
            evidence_ids=added_ids,
        )
        tool_results.append(result)
        search_event: dict[str, Any] = {
            "event_type": "node_progress" if added_ids else "node_degraded",
            "gate": "source_collection",
            "agent": "Search Scout",
            "message": (
                f"搜索完成：{intent.intent}，原始 {len(raw_results)} 条，"
                f"采纳 {len(added_ids)} 条，过滤/重复 {len(raw_results) - len(added_ids)} 条"
            ),
            "progress_current": index,
            "progress_total": max(1, len(intents)),
            "data": result.model_dump(mode="json"),
        }
        if not added_ids:
            search_event["severity"] = "warning"
        await emit_event(RunEvent(**search_event))
    return tool_results


def _search_rejection_summary(
    raw_results: list[SearchResult],
    accepted: list[SearchResult],
    project: ResearchProject,
) -> list[str]:
    accepted_urls = {item.url for item in accepted}
    reasons: list[str] = []
    for result in raw_results:
        if result.url in accepted_urls:
            continue
        parsed = urlparse(result.url)
        hostname = (parsed.hostname or "").lower()
        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in _V1_BLOCKED_DOMAINS):
            reasons.append("blocked_domain")
        elif parsed.path.lower().endswith(_V1_ATTACHMENT_EXTENSIONS):
            reasons.append("attachment")
        elif len(_clean_search_snippet(result.snippet, fallback="")) < 40:
            reasons.append("thin_snippet")
        elif not _is_v1_result_topic_relevant(project.domain, result.title, _clean_search_snippet(result.snippet, fallback="")):
            reasons.append("topic_mismatch")
        else:
            reasons.append("duplicate_or_low_signal")
    return list(dict.fromkeys(reasons))[:6]


async def _evaluate_coverage_with_master_agent(
    *,
    project: ResearchProject,
    evidence: list[EvidenceItem],
    memory: RunWorkingMemory,
    llm_provider: LLMProvider | None,
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> CoverageReport:
    fallback = _fallback_coverage_report(project, evidence, memory)
    report = fallback
    if llm_provider is not None and evidence:
        prompt = (
            "你是 SectorBreaker 的 Master Agent，请判断当前资料是否足以开始生成 Obsidian 领域知识库。"
            "不要只看证据条数，要按维度判断：概念边界、现状、趋势、政策/风险、案例/玩家、用户需求、信源质量。"
            "如果资料明显不足，应返回 needs_more_sources；如果 0 证据必须 blocked；"
            "如果可以继续但资料薄弱，返回 degraded 并说明缺口。\n\n"
            f"研究目标：{memory.objective}\n"
            f"领域：{project.domain}\n"
            f"搜索轮次：{memory.search_round}/{_V1_MASTER_MAX_SEARCH_ROUNDS}\n"
            f"上传材料：{[item.model_dump(mode='json') for item in memory.document_sources]}\n"
            f"工具结果：{[item.model_dump(mode='json') for item in memory.tool_results[-8:]]}\n"
            f"证据摘要：{_evidence_brief(evidence)}"
        )
        try:
            generated = await llm_provider.complete_structured([ChatMessage(role="user", content=prompt)], CoverageReport)
            if isinstance(generated, CoverageReport):
                report = _normalize_coverage_report(generated, fallback, evidence, memory)
        except Exception as exc:
            await emit_event(RunEvent(
                event_type="node_degraded",
                gate="coverage_evaluation",
                agent="Master Agent",
                message=f"LLM 覆盖判断失败，已使用本地覆盖评估：{type(exc).__name__}",
                progress_current=len(evidence),
                progress_total=_V1_TARGET_EVIDENCE_COUNT,
                severity="warning",
            ))

    coverage_event: dict[str, Any] = {
        "event_type": "node_progress" if report.can_continue else "node_degraded",
        "gate": "coverage_evaluation",
        "agent": "Master Agent",
        "message": (
            f"覆盖评估：{report.status}，得分 {report.coverage_score:.2f}；"
            f"已覆盖 {', '.join(report.covered_dimensions) or '暂无'}；"
            f"缺口 {', '.join(report.missing_dimensions) or '暂无'}"
        ),
        "progress_current": len(evidence),
        "progress_total": max(_V1_TARGET_EVIDENCE_COUNT, len(evidence)),
        "data": report.model_dump(mode="json"),
    }
    if not report.can_continue or report.status == "degraded":
        coverage_event["severity"] = "warning"
    await emit_event(RunEvent(**coverage_event))
    return report


def _fallback_coverage_report(
    project: ResearchProject,
    evidence: list[EvidenceItem],
    memory: RunWorkingMemory,
) -> CoverageReport:
    if not evidence:
        return CoverageReport(
            status="blocked",
            can_continue=False,
            coverage_score=0.0,
            covered_dimensions=[],
            missing_dimensions=[
                "concept_boundary",
                "current_state",
                "trends_reports",
                "policy_risk",
                "cases_players",
                "user_demand",
                "source_quality",
            ],
            reason="当前没有任何可用证据，无法生成可信知识库。",
            block_reason=_V1_ZERO_EVIDENCE_BLOCK_MESSAGE,
        )

    covered = _covered_dimensions_from_evidence(evidence, memory)
    required = [
        "concept_boundary",
        "current_state",
        "trends_reports",
        "policy_risk",
        "cases_players",
        "user_demand",
        "source_quality",
    ]
    missing = [item for item in required if item not in covered]
    score = min(1.0, (len(covered) / len(required)) * 0.75 + min(len(evidence), 12) / 12 * 0.25)
    has_external_report = any(item.channel == "assistant_brief" for item in memory.document_sources)
    has_user_material = any(item.channel != "assistant_brief" for item in memory.document_sources)
    exhausted_rounds = memory.search_round >= _V1_MASTER_MAX_SEARCH_ROUNDS

    if score >= 0.68 and len(covered) >= 5 and len(evidence) >= 4:
        status = "sufficient"
        can_continue = True
        reason = "当前资料已覆盖多个核心维度，可进入知识建库。"
    elif project.source_policy == SourcePolicy.USER_MATERIALS_ONLY and (has_external_report or has_user_material):
        status = "degraded"
        can_continue = True
        reason = "用户选择仅用户材料，Master Agent 将基于上传材料降级建库并保留缺口。"
    elif (has_external_report or has_user_material) and len(evidence) >= 2 and score >= 0.38:
        status = "degraded"
        can_continue = True
        reason = "上传报告/材料已提供基础上下文，但仍需标记未验证缺口。"
    elif exhausted_rounds and len(evidence) > 0:
        status = "degraded"
        can_continue = True
        reason = "已达到本轮最大搜索轮次，仍有覆盖缺口，将降级生成待补证知识库。"
    else:
        status = "needs_more_sources"
        can_continue = False
        reason = "资料仍缺少关键维度，Master Agent 将继续搜索。"

    return CoverageReport(
        status=status,
        can_continue=can_continue,
        coverage_score=round(score, 2),
        covered_dimensions=covered,
        missing_dimensions=missing,
        next_search_intents=[
            intent for intent in _fallback_search_plan(project=project, memory=memory, round_index=memory.search_round + 1).intents
            if any(_normalize_dimension_id(dim) in missing for dim in intent.coverage_dimensions)
        ][:_V1_MASTER_MAX_INTENTS_PER_ROUND],
        reason=reason,
        block_reason=None if can_continue or status == "needs_more_sources" else "资料覆盖不足，无法继续。",
    )


def _normalize_coverage_report(
    generated: CoverageReport,
    fallback: CoverageReport,
    evidence: list[EvidenceItem],
    memory: RunWorkingMemory,
) -> CoverageReport:
    status = generated.status if generated.status in {"sufficient", "needs_more_sources", "blocked", "degraded"} else fallback.status
    can_continue = generated.can_continue
    if not evidence:
        status = "blocked"
        can_continue = False
    if status == "sufficient" and len(evidence) < 4 and not memory.document_sources and memory.search_round < _V1_MASTER_MAX_SEARCH_ROUNDS:
        status = "needs_more_sources"
        can_continue = False
    if status == "blocked":
        can_continue = False
    if status in {"sufficient", "degraded"}:
        can_continue = True
    missing = [_normalize_dimension_id(item) for item in generated.missing_dimensions] or fallback.missing_dimensions
    covered = [_normalize_dimension_id(item) for item in generated.covered_dimensions] or fallback.covered_dimensions
    return CoverageReport(
        status=status,
        can_continue=can_continue,
        coverage_score=max(0.0, min(1.0, generated.coverage_score or fallback.coverage_score)),
        covered_dimensions=list(dict.fromkeys(covered)),
        missing_dimensions=list(dict.fromkeys(missing)),
        next_search_intents=generated.next_search_intents or fallback.next_search_intents,
        reason=generated.reason or fallback.reason,
        block_reason=generated.block_reason or fallback.block_reason,
    )


def _covered_dimensions_from_evidence(evidence: list[EvidenceItem], memory: RunWorkingMemory) -> list[str]:
    text = " ".join(
        f"{item.source_title or ''} {item.snippet or ''} {item.summary or ''}".lower()
        for item in evidence
    )
    dimension_keywords = {
        "concept_boundary": ("概念", "术语", "定义", "边界", "入门", "guide", "overview", "framework"),
        "current_state": ("现状", "市场", "规模", "应用", "发展", "adoption", "market", "industry"),
        "trends_reports": ("趋势", "报告", "数据", "增长", "2025", "2026", "trend", "report"),
        "policy_risk": ("政策", "监管", "风险", "合规", "治理", "安全", "regulation", "risk", "governance"),
        "cases_players": ("案例", "公司", "玩家", "平台", "工具", "框架", "实践", "case", "company", "tool"),
        "user_demand": ("用户", "需求", "痛点", "学习", "岗位", "就业", "技能", "question", "demand", "skill"),
    }
    covered = [
        dimension
        for dimension, keywords in dimension_keywords.items()
        if any(keyword in text for keyword in keywords)
    ]
    unique_urls = {item.source_url for item in evidence if item.source_url}
    trusted_channels = {SourceChannel.USER_UPLOAD, SourceChannel.MANUAL_LINK, SourceChannel.SEARCH}
    if len(unique_urls) >= 3 or any(item.source_channel in trusted_channels for item in evidence) or memory.document_sources:
        covered.append("source_quality")
    return list(dict.fromkeys(covered))


def _normalize_dimension_id(value: str) -> str:
    normalized = value.strip().lower()
    alias_map = {
        "concepts": "concept_boundary",
        "concept": "concept_boundary",
        "概念": "concept_boundary",
        "边界": "concept_boundary",
        "current": "current_state",
        "current_state": "current_state",
        "现状": "current_state",
        "trend": "trends_reports",
        "trends": "trends_reports",
        "趋势": "trends_reports",
        "policy": "policy_risk",
        "risk": "policy_risk",
        "政策": "policy_risk",
        "风险": "policy_risk",
        "case": "cases_players",
        "cases": "cases_players",
        "players": "cases_players",
        "案例": "cases_players",
        "玩家": "cases_players",
        "demand": "user_demand",
        "user": "user_demand",
        "用户": "user_demand",
        "需求": "user_demand",
        "source": "source_quality",
        "sources": "source_quality",
        "source_quality": "source_quality",
        "信源": "source_quality",
    }
    return alias_map.get(normalized, normalized)


def _decision_from_coverage(coverage: CoverageReport) -> MasterAgentDecision:
    if coverage.status == "blocked":
        action = "block"
    elif coverage.status == "needs_more_sources":
        action = "search_again"
    elif coverage.status == "degraded":
        action = "degrade"
    else:
        action = "continue"
    return MasterAgentDecision(
        action=action,
        reason=coverage.reason or coverage.block_reason or f"coverage status: {coverage.status}",
        coverage_report=coverage,
    )


async def _emit_zero_or_low_evidence_block(
    *,
    project: ResearchProject,
    evidence: list[EvidenceItem],
    search_provider: SearchProvider | None,
    coverage: CoverageReport,
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> None:
    message = coverage.block_reason or coverage.reason or _V1_ZERO_EVIDENCE_BLOCK_MESSAGE
    if not evidence:
        message = _V1_ZERO_EVIDENCE_BLOCK_MESSAGE
    await emit_event(RunEvent(
        event_type="node_blocked",
        gate="source_collection" if not evidence else "coverage_evaluation",
        agent="Master Agent",
        message=message,
        progress_current=len(evidence),
        progress_total=_V1_TARGET_EVIDENCE_COUNT,
        severity="error",
        data={
            "status": "blocked",
            "reason": coverage.status,
            "source_policy": project.source_policy.value,
            "search_configured": search_provider is not None,
            "coverage": coverage.model_dump(mode="json"),
        },
    ))
    raise RuntimeError(message)


def _assess_evidence_sufficiency(evidence: list[EvidenceItem]) -> dict[str, Any]:
    source_urls = {item.source_url for item in evidence if item.source_url}
    evidence_count = len(evidence)
    if evidence_count >= _V1_TARGET_EVIDENCE_COUNT:
        status = "sufficient"
        message = f"资料充足度检查通过：已收集 {evidence_count} 条证据，可进入建库"
    elif evidence_count >= _V1_MIN_ACCEPTABLE_EVIDENCE_COUNT:
        status = "borderline"
        message = f"资料基本可用：已收集 {evidence_count} 条证据，但仍建议后续补充更多信源"
    elif evidence_count > 0:
        status = "insufficient"
        message = (
            f"资料不足：当前只有 {evidence_count} 条证据，低于建议阈值 "
            f"{_V1_MIN_ACCEPTABLE_EVIDENCE_COUNT} 条，本轮会继续生成但应标记为待补证"
        )
    else:
        status = "empty"
        message = "资料不足：当前没有可用搜索证据，本轮只能使用 fallback 框架生成，必须补充信源"
    return {
        "status": status,
        "evidence_count": evidence_count,
        "unique_source_count": len(source_urls),
        "target_evidence_count": _V1_TARGET_EVIDENCE_COUNT,
        "minimum_acceptable_evidence_count": _V1_MIN_ACCEPTABLE_EVIDENCE_COUNT,
        "message": message,
    }


def _search_result_to_evidence(project: ResearchProject, result: SearchResult, index: int) -> EvidenceItem:
    evidence_id = f"EV-V1-{project.id}-{index}"
    snippet = _clean_search_snippet(result.snippet, fallback=result.title)
    return EvidenceItem(
        id=evidence_id,
        project_id=project.id,
        source_title=result.title,
        source_url=result.url,
        source_type="web",
        source_channel=SourceChannel.SEARCH,
        source_policy=project.source_policy.value,
        raw_excerpt=snippet,
        snippet=snippet,
        summary=snippet,
        claims=[
            EvidenceClaim(
                claim_id=f"{evidence_id}-CLAIM-1",
                text=snippet,
                claim_type=ClaimType.GENERAL_FACT,
                support_level=0.55,
                requires_verification=True,
                verification_status=VerificationStatus.PARTIALLY_VERIFIED,
                evidence_ids=[evidence_id],
                notes="V1 搜索结果摘要，需在后续版本做更强网页抽取与交叉验证。",
            )
        ],
        source_quality=SourceQuality.UNKNOWN,
        claim_strength=ClaimStrength.OPINION,
        bias_risk="搜索摘要尚未完整抽取原文，需人工复核。",
        recency=result.published_date,
        needs_counterevidence=True,
        collected_by="v1_pipeline_search",
        confidence=0.55,
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
    )


def _build_v1_search_query(domain: str) -> str:
    domain_text = domain.strip()
    if "agent" in domain_text.lower() or "智能体" in domain_text:
        return (
            '"AI Agent" development frameworks engineering production '
            'evaluation orchestration MCP LangGraph OpenAI Agents SDK 2026'
        )
    if "大模型" in domain_text or "llm" in domain_text.lower():
        return (
            f"{domain_text} 大模型应用开发 岗位 技能要求 RAG Agent "
            "模型API Python LangChain LangGraph 就业方向 2026"
        )
    return (
        f"{domain_text} 行业趋势 市场规模 政策监管 主要玩家 "
        "用户需求 商业模式 研究报告 案例 2026"
    )


def _build_v1_supplemental_search_query(domain: str) -> str:
    domain_text = domain.strip()
    return (
        f"{domain_text} 权威资料 官方信息 研究报告 数据报告 "
        "实践案例 关键概念 入门指南 风险问题 2026"
    )


def _filter_v1_search_results(results: list[SearchResult], *, project: ResearchProject) -> list[SearchResult]:
    return [result for result in results if _is_v1_search_result_usable(result, project=project)]


def _is_v1_search_result_usable(result: SearchResult, *, project: ResearchProject) -> bool:
    parsed = urlparse(result.url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    title = result.title.lower()
    if any(hostname == domain or hostname.endswith(f".{domain}") for domain in _V1_BLOCKED_DOMAINS):
        return False
    if path.endswith(_V1_ATTACHMENT_EXTENSIONS):
        return False
    if any(marker in title for marker in _V1_LOW_SIGNAL_TITLE_MARKERS):
        return False
    cleaned = _clean_search_snippet(result.snippet, fallback="")
    if len(cleaned) < 40:
        return False
    if not _is_v1_result_topic_relevant(project.domain, result.title, cleaned):
        return False
    return True


def _is_v1_result_topic_relevant(domain: str, title: str, cleaned_snippet: str) -> bool:
    text = f"{title} {cleaned_snippet}".lower()
    domain_text = domain.lower()
    if "agent" in domain_text or "智能体" in domain_text:
        ai_markers = ("ai", "agentic", "llm", "大模型", "智能体", "人工智能")
        agent_markers = ("agent", "agents", "智能体")
        return any(marker in text for marker in ai_markers) and any(marker in text for marker in agent_markers)
    if "大模型" in domain_text or "llm" in domain_text:
        model_markers = ("大模型", "llm", "large model", "模型api", "模型 api", "rag", "agent")
        career_markers = ("就业", "岗位", "招聘", "职业", "技能", "薪", "工程师", "开发")
        return any(marker in text for marker in model_markers) and any(marker in text for marker in career_markers)

    tokens = _topic_tokens(domain_text)
    if not tokens:
        return True
    if any(token in text for token in tokens if len(token) >= 3):
        return True
    short_hits = [token for token in tokens if len(token) == 2 and token in text]
    return len(short_hits) >= 2


def _topic_tokens(domain_text: str) -> list[str]:
    normalized = domain_text.strip().lower()
    split_tokens = [
        token
        for token in re.split(r"[\s,，;；/|]+", normalized)
        if len(token) >= 2
    ]
    tokens = split_tokens or ([normalized] if normalized else [])
    tokens.extend(marker for marker in _CHINESE_TOPIC_MARKERS if marker in normalized)

    chinese_sequences = re.findall(r"[\u4e00-\u9fff]{4,}", normalized)
    for sequence in chinese_sequences:
        max_len = min(6, len(sequence))
        for size in range(max_len, 1, -1):
            for index in range(0, len(sequence) - size + 1):
                token = sequence[index:index + size]
                if len(token) == 2 and token in _GENERIC_SHORT_TOPIC_TOKENS:
                    continue
                tokens.append(token)
    return list(dict.fromkeys(tokens))


def _clean_search_snippet(raw_text: str | None, *, fallback: str = "") -> str:
    """Turn provider snippets into short, readable evidence text before persistence."""

    text = (raw_text or "").strip()
    if not text:
        return fallback.strip()[:_V1_SNIPPET_MAX_CHARS] or "搜索结果未提供摘要，需打开来源复核。"

    text = _MARKDOWN_IMAGE_RE.sub("", text)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _RAW_URL_RE.sub("", text)
    text = text.replace("|", " ")
    text = text.replace("`", "")
    text = text.replace("*", " ")
    text = text.replace("#", " ")
    text = text.replace("•", " ")
    text = _WHITESPACE_RE.sub(" ", text).strip(" -;:，")

    chunks = re.split(r"(?<=[。.!?])\s+|\s{2,}", text)
    clean_chunks: list[str] = []
    for chunk in chunks:
        normalized = chunk.strip(" -;:，")
        if not normalized:
            continue
        lowered = normalized.lower()
        if any(marker in lowered for marker in _SEARCH_SNIPPET_NOISE_MARKERS):
            continue
        if lowered.count("github") >= 3 and len(normalized) < 160:
            continue
        clean_chunks.append(normalized)

    cleaned = " ".join(clean_chunks).strip()
    if not cleaned:
        cleaned = fallback.strip() or "搜索结果摘要主要是页面导航，需打开来源复核。"

    return _truncate_text(cleaned, _V1_SNIPPET_MAX_CHARS)


def _truncate_text(text: str, max_chars: int) -> str:
    normalized = _WHITESPACE_RE.sub(" ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip(" ,.;:，。") + "…"


async def _complete_structured_with_heartbeat(
    *,
    llm_provider: LLMProvider,
    messages: list[ChatMessage],
    response_schema: type[Any],
    emit_event: Callable[[RunEvent], Awaitable[None]],
    gate: str,
    agent: str,
    waiting_message: str,
    progress_current: int,
    progress_total: int,
    interval_seconds: float = 15,
) -> Any:
    task = asyncio.create_task(llm_provider.complete_structured(messages, response_schema))
    heartbeat_count = 0
    while not task.done():
        done, _ = await asyncio.wait({task}, timeout=interval_seconds)
        if done:
            break
        heartbeat_count += 1
        await emit_event(RunEvent(
            event_type="node_progress",
            gate=gate,
            agent=agent,
            message=f"{waiting_message}（已等待约 {int(heartbeat_count * interval_seconds)} 秒）",
            progress_current=progress_current,
            progress_total=progress_total,
        ))
    return await task


async def _build_knowledge_database(
    *,
    project: ResearchProject,
    evidence: list[EvidenceItem],
    llm_provider: LLMProvider | None,
    emit_event: Callable[[RunEvent], Awaitable[None]] | None = None,
) -> DomainKnowledgeBase:
    fallback = _fallback_database(project, evidence)
    if llm_provider is None:
        return fallback

    prompt = (
        "你是 SectorBreaker 的领域建库 Agent。请不要写行业报告，而是构建可导入 Obsidian 的结构化知识库。"
        "只聚焦学习和理解一个陌生领域：概念、主流架构、工具框架、趋势、学习路径、待验证问题。"
        "不要输出竞品收入结构或内容生态分析。每个对象尽量引用 evidence_ids。\n\n"
        f"项目：{project.title}\n领域：{project.domain}\n市场范围：{project.market_scope.value}\n"
        f"证据：{_evidence_brief(evidence)}"
    )
    try:
        messages = [ChatMessage(role="user", content=prompt)]
        if emit_event is None:
            generated = await llm_provider.complete_structured(messages, DomainKnowledgeBase)
        else:
            generated = await _complete_structured_with_heartbeat(
                llm_provider=llm_provider,
                messages=messages,
                response_schema=DomainKnowledgeBase,
                emit_event=emit_event,
                gate="knowledge_structuring",
                agent="Knowledge Builder",
                waiting_message="仍在生成结构化领域库，正在让 LLM 整合证据",
                progress_current=1,
                progress_total=2,
            )
    except Exception as exc:
        if emit_event is not None:
            await emit_event(RunEvent(
                event_type="node_degraded",
                gate="knowledge_structuring",
                agent="Knowledge Builder",
                message=f"LLM 结构化领域库生成失败，已使用保底知识库骨架：{type(exc).__name__}",
                progress_current=1,
                progress_total=2,
                severity="warning",
            ))
        return fallback
    if not isinstance(generated, DomainKnowledgeBase):
        if emit_event is not None:
            await emit_event(RunEvent(
                event_type="node_degraded",
                gate="knowledge_structuring",
                agent="Knowledge Builder",
                message="LLM 未返回有效领域库结构，已使用保底知识库骨架",
                progress_current=1,
                progress_total=2,
                severity="warning",
            ))
        return fallback
    return _merge_database_with_fallback(generated, fallback)


def _fallback_database(project: ResearchProject, evidence: list[EvidenceItem]) -> DomainKnowledgeBase:
    evidence_ids = [item.id for item in evidence] or ["待补充证据"]
    topic = project.domain
    evidence_themes = _evidence_theme_lines(evidence)
    if "大模型" in topic or "llm" in topic.lower():
        return _large_model_career_database(project, evidence, evidence_ids, evidence_themes)
    if "agent" in topic.lower() or "智能体" in topic:
        return _agent_development_database(project, evidence, evidence_ids, evidence_themes)
    draft_label = "待补证草稿：" if not evidence else ""
    return DomainKnowledgeBase(
        overview=(
            f"{draft_label}{topic} 知识库用于先抹平信息差：建立领域边界、关键术语、"
            "参与者结构、用户需求、交付流程、工具/方法和待验证问题。"
            f"当前版本基于 {len(evidence)} 条证据生成。"
            f"{' 证据主题包括：' + evidence_themes if evidence_themes else ' 由于证据不足，以下内容仅能作为继续补资料的结构化框架。'}"
        ),
        concepts=[
            DomainConcept(
                name=f"{topic} 领域边界",
                definition=f"说明 {topic} 主要覆盖哪些对象、问题、用户场景和服务形态，并排除容易混淆的相邻领域。",
                why_it_matters="先划清边界，后续搜索、学习和判断才不会被无关信息带偏。",
                related=["目标用户", "核心场景", "相邻领域"],
                evidence_ids=evidence_ids[:2],
            ),
            DomainConcept(
                name="核心术语",
                definition=f"进入 {topic} 前需要先掌握的基础概念、常见缩写、评价口径和行业黑话。",
                why_it_matters="术语是阅读报告、比较方案和继续提问的索引，缺少术语表会导致信息越看越散。",
                related=["概念卡片", "评价指标", "常见问题"],
                evidence_ids=evidence_ids[:2],
            ),
            DomainConcept(
                name="需求与用户",
                definition=f"识别谁会使用或购买 {topic} 相关产品/服务，他们要解决什么问题，决策链条如何发生。",
                why_it_matters="理解需求侧，才能判断哪些信息是关键事实，哪些只是泛泛介绍。",
                related=["用户画像", "使用场景", "痛点"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainConcept(
                name="供给与参与者",
                definition=f"梳理 {topic} 中提供产品、服务、内容、渠道或基础设施的主要角色。",
                why_it_matters="供给结构决定学习时应该看哪些公司、机构、平台、社区或政策来源。",
                related=["主要玩家", "服务链条", "信源地图"],
                evidence_ids=evidence_ids[:3],
            ),
        ],
        architectures=[
            DomainArchitecture(
                name="供给链 / 服务链路",
                summary=f"把 {topic} 从上游资源、核心服务、渠道触达、用户交付到反馈复购拆成一条链路。",
                use_cases=["理解行业地图", "定位关键参与者", "判断资料缺口"],
                strengths=["适合快速建立全局结构", "便于把零散来源放回正确位置"],
                limitations=["证据不足时只能形成假设，需要继续补充真实案例和数据"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainArchitecture(
                name="用户旅程",
                summary=f"从用户第一次接触 {topic}、比较选择、实际使用、评价结果到继续购买/退出的全过程。",
                use_cases=["发现关键痛点", "设计学习路线", "判断哪些结论需要用户侧证据"],
                strengths=["能把抽象领域转成具体行为", "适合发现真实问题"],
                limitations=["需要访谈、评论、案例或数据支撑，否则容易停留在推测"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainArchitecture(
                name="能力栈 / 工具栈",
                summary=f"完成 {topic} 相关任务所需的知识、工具、方法、平台和评价指标组合。",
                use_cases=["制定入门路线", "比较工具方案", "生成 Obsidian 知识卡片"],
                strengths=["把学习任务拆得更可执行", "便于后续补充教程和案例"],
                limitations=["不同细分场景差异较大，需要按目标继续细化"],
                evidence_ids=evidence_ids[:3],
            ),
        ],
        tools=[
            DomainTool(
                name="官方/机构信息源",
                category="source",
                use_case=f"查找 {topic} 的政策、标准、统计、机构说明、公司公告或公开报告。",
                tradeoffs="可信度较高，但覆盖不一定完整，可能不够贴近一线体验。",
                evidence_ids=evidence_ids[:3],
            ),
            DomainTool(
                name="案例与用户反馈",
                category="source",
                use_case=f"通过案例、评论、问答、社区讨论理解 {topic} 的真实使用方式和痛点。",
                tradeoffs="贴近实际，但偏主观，需要和可靠来源交叉验证。",
                evidence_ids=evidence_ids[:3],
            ),
            DomainTool(
                name="研究报告与数据文章",
                category="source",
                use_case=f"获得 {topic} 的规模、趋势、参与者、增长驱动和风险判断。",
                tradeoffs="信息密度高，但要注意发布时间、样本口径、商业立场和引用来源。",
                evidence_ids=evidence_ids[:3],
            ),
        ],
        trends=[
            f"{topic} 的趋势判断应优先来自近期政策、行业报告、用户行为变化和真实案例。",
            "如果来源不足，趋势只能作为待验证假设，不应写成确定结论。",
            "后续补库应优先寻找能说明规模、需求变化、参与者变化和监管/技术约束的来源。",
        ],
        learning_path=[
            f"先建立 {topic} 的领域边界和术语表；完成标志：能解释这个领域解决什么问题、服务谁、和哪些相邻领域不同。",
            "再梳理供给链和用户旅程；完成标志：能画出主要参与者、用户决策过程和关键交付节点。",
            "继续补主流案例和信息源；完成标志：每个重要判断至少能回链到一条来源。",
            "形成自己的 Obsidian 知识卡片；完成标志：概念、问题、来源、趋势之间能通过双向链接串起来。",
            "最后列出待验证问题并滚动补库；完成标志：知道下一轮应该搜索什么、问什么、验证什么。",
        ],
        open_questions=[
            f"{topic} 的权威信源有哪些？哪些来源只是营销或二手总结？",
            "这个领域的核心概念、评价指标和常见误区分别是什么？",
            "近两年有哪些政策、技术、用户需求或商业模式变化？",
            "主要参与者、典型案例和用户痛点是否有足够证据支撑？",
            "如果要继续学习或入局，第一批可执行的小项目/调研任务是什么？",
        ],
    )


def _agent_development_database(
    project: ResearchProject,
    evidence: list[EvidenceItem],
    evidence_ids: list[str],
    evidence_themes: str,
) -> DomainKnowledgeBase:
    topic = project.domain
    return DomainKnowledgeBase(
        overview=(
            f"{topic} 知识库用于理解 Agent 开发的核心术语、主流架构、工具框架、工程化趋势和学习路径。"
            f"当前版本基于 {len(evidence)} 条搜索证据生成。"
            f"{' 证据主题包括：' + evidence_themes if evidence_themes else ' 由于证据不足，以下内容均应作为待验证学习框架。'}"
        ),
        concepts=[
            DomainConcept(
                name="AI Agent",
                definition="围绕目标自主感知、推理、规划、调用工具并执行动作的软件系统。",
                why_it_matters="它是理解工具调用、工作流编排、多 Agent 协作和生产落地的共同入口。",
                related=["工具调用", "规划", "记忆", "评测"],
                evidence_ids=evidence_ids[:2],
            ),
            DomainConcept(
                name="工具调用",
                definition="模型通过函数、API、MCP Server、浏览器或业务系统接口完成实际动作。",
                why_it_matters="没有工具调用，Agent 往往只能停留在问答；有工具调用才可能进入真实工作流。",
                related=["MCP", "函数调用", "权限控制"],
                evidence_ids=evidence_ids[:2],
            ),
            DomainConcept(
                name="规划与执行",
                definition="把目标拆解成步骤，选择下一步动作，并根据反馈修正计划。",
                why_it_matters="复杂任务的可靠性取决于规划、执行、验证和恢复机制是否清晰。",
                related=["Planner-Executor", "ReAct", "Workflow Agent"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainConcept(
                name="记忆与上下文",
                definition="保存任务状态、用户偏好、外部知识和历史决策，以支持跨步骤推理。",
                why_it_matters="长期任务、个性化助手和组织知识库都依赖可管理的记忆机制。",
                related=["RAG", "向量数据库", "知识图谱"],
                evidence_ids=evidence_ids[:3],
            ),
        ],
        architectures=[
            DomainArchitecture(
                name="Planner-Executor",
                summary="先由规划器拆任务，再由执行器逐步调用工具完成任务。",
                use_cases=["研究助理", "代码生成", "多步骤自动化"],
                strengths=["结构清晰", "容易插入人工确认", "便于失败定位"],
                limitations=["计划质量不足时会级联失败", "需要额外验证环节"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainArchitecture(
                name="Workflow Agent",
                summary="把 LLM 能力放入确定性工作流节点，用状态机或图控制步骤。",
                use_cases=["生产系统", "审批流", "可观测自动化"],
                strengths=["可控性强", "便于测试", "适合工程落地"],
                limitations=["灵活性低于开放式 Agent", "前期架构设计成本更高"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainArchitecture(
                name="Multi-Agent",
                summary="多个角色 Agent 分工协作，例如研究、批判、执行、总结。",
                use_cases=["复杂研究", "代码审查", "多视角决策"],
                strengths=["角色边界清晰", "可引入反证和复核"],
                limitations=["协调成本高", "容易产生重复、漂移和上下文浪费"],
                evidence_ids=evidence_ids[:3],
            ),
        ],
        tools=[
            DomainTool(
                name="LangGraph",
                category="workflow",
                use_case="构建有状态、多节点、可暂停恢复的 Agent 工作流。",
                tradeoffs="适合生产控制，但需要认真设计 state、node、edge 和检查点。",
                evidence_ids=evidence_ids[:3],
            ),
            DomainTool(
                name="OpenAI Agents SDK",
                category="sdk",
                use_case="快速搭建工具调用、handoff 和 Agent 编排。",
                tradeoffs="上手快，复杂业务仍需要额外的状态、权限和评测体系。",
                evidence_ids=evidence_ids[:3],
            ),
            DomainTool(
                name="CrewAI / AutoGen",
                category="multi-agent",
                use_case="快速试验角色分工式多 Agent 协作。",
                tradeoffs="适合原型，生产落地时要警惕不可控循环和上下文成本。",
                evidence_ids=evidence_ids[:3],
            ),
        ],
        trends=[
            "Agent 开发正在从 demo 转向工程化：状态管理、可观测性、评测和权限控制变得更重要。",
            "MCP、函数调用和工具生态正在把 Agent 从聊天界面连接到真实系统。",
            "评测 Agent Development Kits 和生产可靠性正在成为框架选择的重要依据。",
        ],
        learning_path=[
            "先理解 AI Agent、工具调用、规划、记忆、RAG、MCP 等基础概念；完成标志：能解释每个概念解决什么问题。",
            "比较 Planner-Executor、Workflow Agent、Multi-Agent、RAG Agent 等主流架构；完成标志：能判断一个任务适合哪类架构。",
            "选择一个框架做最小项目，例如 LangGraph 或 OpenAI Agents SDK；完成标志：能跑通工具调用和错误处理。",
            "补充工程化能力：日志、评测、权限、人工确认、失败恢复；完成标志：能说明 demo 到生产缺什么。",
            "把自己的学习笔记转成 Obsidian 卡片，并持续补证据；完成标志：每个关键判断都能回链来源。",
        ],
        open_questions=[
            "哪些框架在生产环境中最稳定，证据来自哪里？",
            "不同架构的失败模式分别是什么？",
            "MCP、函数调用、浏览器自动化在真实产品中如何分工？",
            "哪些能力是学习入门必须掌握，哪些只是高级工程化需求？",
        ],
    )


def _large_model_career_database(
    project: ResearchProject,
    evidence: list[EvidenceItem],
    evidence_ids: list[str],
    evidence_themes: str,
) -> DomainKnowledgeBase:
    topic = project.domain
    return DomainKnowledgeBase(
        overview=(
            f"{topic} 知识库用于快速理解大模型应用开发相关岗位、技能栈、学习路径和就业判断。"
            f"当前版本基于 {len(evidence)} 条搜索证据生成。"
            f"{' 证据主题包括：' + evidence_themes if evidence_themes else ' 由于证据不足，以下内容均应作为待验证学习框架。'}"
        ),
        concepts=[
            DomainConcept(
                name="大模型应用开发",
                definition="围绕大模型 API、提示词、RAG、Agent、工作流和业务系统集成构建可用应用的工程方向。",
                why_it_matters="多数就业机会不要求训练基础模型，而是要求把模型能力接入真实业务场景。",
                related=["RAG", "Agent", "模型 API", "工程化"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainConcept(
                name="RAG",
                definition="通过检索外部知识并注入上下文，让大模型基于企业文档、知识库或网页资料回答问题。",
                why_it_matters="RAG 是大模型应用开发岗位最常见的落地能力之一，连接搜索、向量数据库和业务知识。",
                related=["向量数据库", "Embedding", "知识库问答"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainConcept(
                name="Agent 开发",
                definition="让模型围绕目标进行规划、调用工具、执行任务并根据反馈调整。",
                why_it_matters="招聘描述里常把 Agent、工具调用、工作流编排作为应用层岗位的进阶要求。",
                related=["工具调用", "LangGraph", "MCP", "Workflow"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainConcept(
                name="模型 API 与工程集成",
                definition="调用商业或开源模型服务，并处理鉴权、限流、成本、日志、异常和业务系统接入。",
                why_it_matters="就业岗位更看重能否把模型稳定接进产品，而不只是会写 prompt。",
                related=["OpenAI-compatible API", "FastAPI", "异步任务", "可观测性"],
                evidence_ids=evidence_ids[:3],
            ),
        ],
        architectures=[
            DomainArchitecture(
                name="RAG 应用架构",
                summary="文档切分、向量化、检索、重排、上下文注入和回答生成组成的知识库应用架构。",
                use_cases=["企业知识库", "客服问答", "文档助手"],
                strengths=["就业需求常见", "容易做作品集", "能体现工程能力"],
                limitations=["依赖数据质量", "需要评测召回率和幻觉问题"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainArchitecture(
                name="Agent 工作流架构",
                summary="把模型调用、工具调用、人工确认、状态管理和导出动作组织成可控流程。",
                use_cases=["研究助手", "办公自动化", "代码/数据处理助手"],
                strengths=["能体现复杂任务编排能力", "适合做进阶项目"],
                limitations=["调试成本高", "需要防止失控循环和错误级联"],
                evidence_ids=evidence_ids[:3],
            ),
            DomainArchitecture(
                name="模型应用后端架构",
                summary="用后端服务封装模型 API、缓存、队列、日志、权限和业务接口。",
                use_cases=["AI SaaS", "企业内部工具", "智能客服"],
                strengths=["贴近真实岗位", "能展示完整工程链路"],
                limitations=["需要后端、部署和成本控制能力"],
                evidence_ids=evidence_ids[:3],
            ),
        ],
        tools=[
            DomainTool(
                name="Python",
                category="language",
                use_case="大模型应用开发、数据处理、后端 API、脚本自动化的主力语言。",
                tradeoffs="生态成熟，但需要补工程结构、测试和部署能力。",
                evidence_ids=evidence_ids[:3],
            ),
            DomainTool(
                name="LangChain / LangGraph",
                category="framework",
                use_case="构建 RAG、工具调用、Agent 工作流和可控状态图。",
                tradeoffs="生态资料多，但抽象层较多，学习时要回到具体数据流和状态流。",
                evidence_ids=evidence_ids[:3],
            ),
            DomainTool(
                name="向量数据库",
                category="infrastructure",
                use_case="支撑 RAG 检索，常见选择包括 Milvus、Qdrant、Chroma、pgvector。",
                tradeoffs="入门容易，真正做好需要理解切分、召回、重排和评测。",
                evidence_ids=evidence_ids[:3],
            ),
            DomainTool(
                name="FastAPI / 后端服务",
                category="backend",
                use_case="把模型能力封装成可被前端或业务系统调用的 API。",
                tradeoffs="能体现就业项目完整度，但需要关注异常、鉴权、异步和部署。",
                evidence_ids=evidence_ids[:3],
            ),
        ],
        trends=[
            "大模型就业机会更偏向应用开发和业务集成，而不是人人都去训练基础模型。",
            "RAG、Agent、模型 API 调用、Python 工程能力和业务理解正在成为应用层岗位关键词。",
            "作品集需要从 demo 走向可部署项目：日志、评测、错误处理和成本控制会显著拉开差距。",
        ],
        learning_path=[
            "先学大模型应用开发边界：API 调用、Prompt、上下文窗口、成本和限流；完成标志：能写一个稳定调用模型的后端接口。",
            "学习 RAG 基础：文档切分、Embedding、向量检索、重排和回答生成；完成标志：能做一个可评测的知识库问答项目。",
            "学习 Agent 与工具调用：函数调用、MCP、工作流编排和状态管理；完成标志：能做一个会调用工具并记录步骤的任务助手。",
            "补工程化能力：FastAPI、数据库、异步任务、日志、权限、部署；完成标志：能把项目部署并给别人试用。",
            "整理就业作品集：岗位 JD 关键词、项目说明、技术难点、效果评测；完成标志：能用项目证明自己具备岗位要求。",
        ],
        open_questions=[
            "目标岗位到底要求模型训练、应用开发还是业务集成？",
            "招聘 JD 中最常出现的技能关键词是什么？",
            "哪些项目最能证明大模型应用开发能力？",
            "RAG、Agent、微调、模型部署分别对应哪些岗位层级？",
        ],
    )


def _merge_database_with_fallback(generated: DomainKnowledgeBase, fallback: DomainKnowledgeBase) -> DomainKnowledgeBase:
    return DomainKnowledgeBase(
        overview=generated.overview or fallback.overview,
        concepts=generated.concepts if len(generated.concepts) >= 3 else fallback.concepts,
        architectures=generated.architectures if len(generated.architectures) >= 2 else fallback.architectures,
        tools=generated.tools if len(generated.tools) >= 2 else fallback.tools,
        trends=generated.trends or fallback.trends,
        learning_path=generated.learning_path if len(generated.learning_path) >= 4 else fallback.learning_path,
        open_questions=generated.open_questions or fallback.open_questions,
    )


def _evidence_theme_lines(evidence: list[EvidenceItem]) -> str:
    if not evidence:
        return ""
    titles = [item.source_title for item in evidence[:5] if item.source_title]
    return "；".join(titles)


async def _build_knowledge_content(
    *,
    project: ResearchProject,
    evidence: list[EvidenceItem],
    llm_provider: LLMProvider | None,
) -> V1KnowledgeContent:
    fallback = _fallback_content(project, evidence)
    if llm_provider is None:
        return fallback

    prompt = (
        "你是 SectorBreaker 的 V1 知识系统生成器。请基于项目主题和证据，输出结构化 Markdown 内容，"
        "不要编造确定性事实；没有证据时明确标注为待验证。\n\n"
        f"项目：{project.title}\n领域：{project.domain}\n市场范围：{project.market_scope.value}\n"
        f"证据：{_evidence_brief(evidence)}"
    )
    try:
        generated = await llm_provider.complete_structured(
            [ChatMessage(role="user", content=prompt)],
            V1KnowledgeContent,
        )
    except Exception:
        return fallback
    if isinstance(generated, V1KnowledgeContent):
        return _merge_generated_with_fallback(generated, fallback)
    return fallback


def _fallback_content(project: ResearchProject, evidence: list[EvidenceItem]) -> V1KnowledgeContent:
    evidence_lines = _evidence_lines(evidence)
    topic = project.domain
    return V1KnowledgeContent(
        domain_overview=(
            f"# {topic} 领域总览\n\n"
            f"- 领域边界：围绕 {topic} 的关键概念、主要参与者、工具链和应用场景。\n"
            f"- 市场范围：{project.market_scope.value}。\n"
            f"- 当前证据：{len(evidence)} 条。\n\n{evidence_lines}"
        ),
        learning_path=(
            "# 入门路线\n\n"
            "1. 先建立领域边界和常见术语。\n"
            "2. 再识别核心工具、玩家和工作流。\n"
            "3. 最后围绕问题、机会和待验证假设做小规模验证。"
        ),
        core_concepts=(
            "# 核心概念\n\n"
            f"- {topic}：本项目的主研究对象。\n"
            "- 工具链：支撑用户完成任务的产品、框架、平台和服务。\n"
            "- 证据 ledger：所有结论应回链到来源或标记为待验证。"
        ),
        player_tool_map=(
            "# 玩家与工具地图\n\n"
            "- 上游：基础模型、数据、基础设施与开发框架。\n"
            "- 中游：工具平台、工作流编排、评测和部署服务。\n"
            "- 下游：行业应用、咨询集成、内容与社区生态。"
        ),
        trend_evidence=f"# 趋势与证据\n\n{evidence_lines}",
        problem_opportunity_map=(
            "# 问题与机会\n\n"
            "- 问题：新用户难以判断学习顺序、工具差异和真实应用边界。\n"
            "- 机会：围绕入门路径、证据化评测、行业模板和落地案例构建可验证产品。"
        ),
        unresolved_questions=(
            "# 待验证问题\n\n"
            "- 哪些事实由高质量来源支持？\n"
            "- 哪些玩家或工具在目标市场中最关键？\n"
            "- 用户最愿意为哪些具体任务付费？"
        ),
    )


def _merge_generated_with_fallback(generated: V1KnowledgeContent, fallback: V1KnowledgeContent) -> V1KnowledgeContent:
    generic_content = generated.content or ""
    sections = "\n".join(f"- {_section_to_markdown(item)}" for item in generated.sections)
    learning_path = _markdown_from_value(generated.learning_path)
    return V1KnowledgeContent(
        domain_overview=generated.domain_overview or generic_content or fallback.domain_overview,
        learning_path=learning_path or fallback.learning_path,
        core_concepts=generated.core_concepts or sections or fallback.core_concepts,
        player_tool_map=generated.player_tool_map or fallback.player_tool_map,
        trend_evidence=generated.trend_evidence or fallback.trend_evidence,
        problem_opportunity_map=generated.problem_opportunity_map or fallback.problem_opportunity_map,
        unresolved_questions=generated.unresolved_questions or fallback.unresolved_questions,
    )


async def _build_artifacts(
    project: ResearchProject,
    database: DomainKnowledgeBase,
    source_evidence_ids: list[str],
    *,
    llm_provider: LLMProvider | None,
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> list[Artifact]:
    now = datetime.now(UTC)
    specs = [
        (ArtifactType.DOMAIN_OVERVIEW, "领域总览", "00-领域总览.md", _render_domain_overview(project, database, source_evidence_ids), "解释这个领域是什么、为什么值得学、全局地图和证据覆盖范围。"),
        (ArtifactType.LEARNING_PATH, "入门路线", "01-入门路线.md", _render_learning_path(project, database), "写出可执行的学习阶梯、每阶段目标、实践任务、完成标志和常见误区。"),
        (ArtifactType.CORE_CONCEPTS, "核心概念", "02-核心概念.md", _render_core_concepts(database), "写出核心概念库，每个概念包含定义、通俗解释、例子、关联概念和证据。"),
        (ArtifactType.PLAYER_TOOL_MAP, "主流架构与工具地图", "03-玩家与工具地图.md", _render_architecture_tool_map(database), "写出主流架构、适用场景、优缺点、工具框架和新手选择建议。"),
        (ArtifactType.TREND_EVIDENCE, "趋势与证据", "04-趋势与证据.md", _render_trends(database), "写出趋势、争议、证据解释、现实约束和需要继续验证的判断。"),
        (ArtifactType.PROBLEM_OPPORTUNITY_MAP, "问题与机会", "05-问题与机会.md", _render_problem_opportunities(project, database), "写出学习者真正会遇到的问题、认知缺口、实践机会和补库策略。"),
        (ArtifactType.UNRESOLVED_QUESTIONS, "待验证问题", "99-待验证问题.md", _render_open_questions(database), "写出后续研究任务，每个问题说明重要性、需要什么证据、下一步怎么查。"),
    ]
    artifacts: list[Artifact] = []
    for index, (artifact_type, title, content_path, fallback_markdown, writing_goal) in enumerate(specs, start=1):
        await emit_event(RunEvent(
            event_type="node_progress",
            gate="document_writing",
            agent="Document Writer",
            message=f"正在写作：{title}",
            progress_current=index,
            progress_total=len(specs),
        ))
        markdown = await _write_artifact_markdown(
            project=project,
            database=database,
            artifact_title=title,
            content_path=content_path,
            writing_goal=writing_goal,
            fallback_markdown=fallback_markdown,
            llm_provider=llm_provider,
            emit_event=emit_event,
            progress_current=index,
            progress_total=len(specs),
        )
        artifacts.append(Artifact(
            id=f"ART-V1-{artifact_type.value.upper()}-{uuid4().hex[:8]}",
            project_id=project.id,
            artifact_type=artifact_type,
            title=title,
            content_path=content_path,
            content=markdown,
            source_evidence_ids=source_evidence_ids,
            schema_version="v1",
            created_at=now,
        ))
    card_artifacts = _build_obsidian_card_artifacts(
        project=project,
        database=database,
        source_evidence_ids=source_evidence_ids,
        created_at=now,
    )
    if card_artifacts:
        await emit_event(RunEvent(
            event_type="node_progress",
            gate="obsidian_export",
            agent="Knowledge Mapper",
            message=(
                f"正在生成 Obsidian 知识卡片：{len(card_artifacts)} 张，"
                "用于支撑主文档中的双向链接"
            ),
            progress_current=1,
            progress_total=1,
        ))
        artifacts.extend(card_artifacts)
    return artifacts


async def _write_artifact_markdown(
    *,
    project: ResearchProject,
    database: DomainKnowledgeBase,
    artifact_title: str,
    content_path: str,
    writing_goal: str,
    fallback_markdown: str,
    llm_provider: LLMProvider | None,
    emit_event: Callable[[RunEvent], Awaitable[None]],
    progress_current: int,
    progress_total: int,
) -> str:
    if llm_provider is None:
        return fallback_markdown

    prompt = (
        "你是 SectorBreaker 的资深研究写作者。你的任务不是复述搜索结果，而是把结构化领域库"
        "写成一份对初学者真正有用、可导入 Obsidian 的 Markdown 文档。\n\n"
        "硬性要求：\n"
        "- 只输出 Markdown 正文，不要 JSON，不要代码块包裹。\n"
        "- 内容要充实，通常不少于 1200 个中文字符；如果信息不足，要写清楚哪些是待验证，而不是写空话。\n"
        "- 每个判断要尽量回链 evidence id，例如 `证据：EV-...`。\n"
        "- 要有解释、关系、例子、学习建议和下一步，不要只列名词。\n"
        "- 关键概念、架构、工具和待验证问题要写成 Obsidian 双向链接，例如 `[[RAG]]`。\n"
        "- 不要写竞品收入结构或内容生态，除非用户主题本身要求。\n\n"
        f"项目：{project.title}\n领域：{project.domain}\n文档：{artifact_title} ({content_path})\n"
        f"写作目标：{writing_goal}\n\n"
        "结构化领域库：\n"
        f"{json.dumps(database.model_dump(mode='json'), ensure_ascii=False, indent=2)}\n\n"
        "如果某部分证据不足，请保留章节并标注“待验证”，但仍要给出学习者可执行的理解框架。"
    )
    try:
        generated = await _complete_structured_with_heartbeat(
            llm_provider=llm_provider,
            messages=[ChatMessage(role="user", content=prompt)],
            response_schema=str,
            emit_event=emit_event,
            gate="document_writing",
            agent="Document Writer",
            waiting_message=f"仍在写作：{artifact_title}，LLM 正在生成 Markdown 正文",
            progress_current=progress_current,
            progress_total=progress_total,
        )
    except Exception as exc:
        await emit_event(RunEvent(
            event_type="node_degraded",
            gate="document_writing",
            agent="Document Writer",
            message=f"LLM 写作失败，已使用保底 Markdown：{artifact_title}（{type(exc).__name__}）",
            progress_current=progress_current,
            progress_total=progress_total,
            severity="warning",
        ))
        return fallback_markdown
    cleaned = _clean_generated_markdown(str(generated))
    if _is_generated_markdown_usable(cleaned):
        return await _review_and_expand_artifact_markdown(
            project=project,
            database=database,
            artifact_title=artifact_title,
            writing_goal=writing_goal,
            markdown=cleaned,
            fallback_markdown=fallback_markdown,
            llm_provider=llm_provider,
            emit_event=emit_event,
            progress_current=progress_current,
            progress_total=progress_total,
        )
    await emit_event(RunEvent(
        event_type="node_degraded",
        gate="document_writing",
        agent="Document Writer",
        message=f"LLM 写作内容过短或结构不足，已使用保底 Markdown：{artifact_title}",
        progress_current=progress_current,
        progress_total=progress_total,
        severity="warning",
        data={"generated_chars": len(cleaned), "heading_count": cleaned.count("\n## ") + cleaned.count("\n### ")},
    ))
    return fallback_markdown


async def _review_and_expand_artifact_markdown(
    *,
    project: ResearchProject,
    database: DomainKnowledgeBase,
    artifact_title: str,
    writing_goal: str,
    markdown: str,
    fallback_markdown: str,
    llm_provider: LLMProvider,
    emit_event: Callable[[RunEvent], Awaitable[None]],
    progress_current: int,
    progress_total: int,
) -> str:
    await emit_event(RunEvent(
        event_type="node_progress",
        gate="artifact_review",
        agent="Artifact Reviewer",
        message=f"正在审查详实度：{artifact_title}",
        progress_current=progress_current,
        progress_total=progress_total,
    ))
    local_needs_expansion = _artifact_needs_detail_expansion(markdown)
    review = ArtifactExpansionReview(
        needs_expansion=local_needs_expansion,
        detail_score=5 if local_needs_expansion else 8,
        missing_angles=["内容篇幅、例子或 Obsidian 链接不足"] if local_needs_expansion else [],
        expansion_brief="补充解释、例子、关联卡片和待验证事项。" if local_needs_expansion else "",
    )
    prompt = (
        "你是 SectorBreaker 的产物审查员。你的任务不是压缩内容，而是判断这篇知识库文档"
        "是否足够详实、具体、可学习、可继续扩展到 Obsidian。\n\n"
        "评分标准：\n"
        "- 详实度：是否有足够解释、例子、上下文、步骤和边界。\n"
        "- 证据使用：是否尽量引用 evidence id，证据不足时是否标注待验证。\n"
        "- 学习价值：读者是否能按它继续学习或补库。\n"
        "- Obsidian 准备度：是否有可链接的概念、架构、工具或问题。\n\n"
        "不要因为有口水话就建议删短；应指出要补哪些角度，让内容更丰富。\n\n"
        f"项目：{project.title}\n领域：{project.domain}\n文档：{artifact_title}\n"
        f"写作目标：{writing_goal}\n\n文档正文：\n{markdown[:6000]}"
    )
    try:
        generated_review = await llm_provider.complete_structured(
            [ChatMessage(role="user", content=prompt)],
            ArtifactExpansionReview,
        )
        if isinstance(generated_review, ArtifactExpansionReview):
            review = generated_review
    except Exception:
        review = review

    if not review.needs_expansion and review.detail_score >= 7 and not local_needs_expansion:
        return markdown

    await emit_event(RunEvent(
        event_type="node_progress",
        gate="artifact_review",
        agent="Artifact Reviewer",
        message=f"发现内容可继续加厚，正在补写：{artifact_title}",
        progress_current=progress_current,
        progress_total=progress_total,
        data=review.model_dump(mode="json"),
    ))
    expansion_prompt = (
        "你是 SectorBreaker 的资深研究写作者。请在保留原文结构和事实边界的基础上，"
        "把这篇文档扩写成更详实的 Obsidian 知识库主文档。\n\n"
        "扩写要求：\n"
        "- 不要删短原文；优先补充解释、例子、学习步骤、反例、边界和待验证问题。\n"
        "- 生成可点击的 Obsidian 双向链接，例如 [[核心概念名]]、[[架构名]]、[[工具名]]。\n"
        "- 没有证据支撑的地方标注“待验证”，不要伪装成确定事实。\n"
        "- 只输出 Markdown 正文，不要 JSON，不要代码块包裹。\n\n"
        f"审查意见：{review.model_dump(mode='json')}\n\n"
        "结构化领域库：\n"
        f"{json.dumps(database.model_dump(mode='json'), ensure_ascii=False, indent=2)}\n\n"
        f"原文：\n{markdown}"
    )
    try:
        expanded = await _complete_structured_with_heartbeat(
            llm_provider=llm_provider,
            messages=[ChatMessage(role="user", content=expansion_prompt)],
            response_schema=str,
            emit_event=emit_event,
            gate="artifact_review",
            agent="Artifact Reviewer",
            waiting_message=f"仍在补写：{artifact_title}，LLM 正在加厚内容",
            progress_current=progress_current,
            progress_total=progress_total,
        )
    except Exception:
        return markdown or fallback_markdown
    cleaned = _clean_generated_markdown(str(expanded))
    if len(cleaned) >= max(len(markdown), 700) and _is_generated_markdown_usable(cleaned):
        return cleaned
    return markdown or fallback_markdown


def _artifact_needs_detail_expansion(markdown: str) -> bool:
    normalized = _WHITESPACE_RE.sub("", markdown)
    heading_count = markdown.count("\n## ") + markdown.count("\n### ")
    has_wikilink = "[[" in markdown and "]]" in markdown
    has_evidence = "EV-" in markdown or "证据" in markdown
    return len(normalized) < 1200 or heading_count < 3 or not has_wikilink or not has_evidence


def _clean_generated_markdown(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _is_generated_markdown_usable(value: str) -> bool:
    if len(value) < 500:
        return False
    return value.count("\n## ") + value.count("\n### ") >= 2


def _build_obsidian_card_artifacts(
    *,
    project: ResearchProject,
    database: DomainKnowledgeBase,
    source_evidence_ids: list[str],
    created_at: datetime,
) -> list[Artifact]:
    artifacts: list[Artifact] = []
    for concept in database.concepts[:16]:
        title = concept.name.strip()
        if not title:
            continue
        evidence_ids = concept.evidence_ids or source_evidence_ids[:5]
        artifacts.append(Artifact(
            id=f"ART-V1-CONCEPT-CARD-{uuid4().hex[:8]}",
            project_id=project.id,
            artifact_type=ArtifactType.CORE_CONCEPTS,
            title=title,
            content_path=f"concepts/{_obsidian_filename(title)}.md",
            content=_render_concept_card(project, concept, evidence_ids),
            source_evidence_ids=evidence_ids,
            schema_version="v1-card",
            created_at=created_at,
        ))
    for architecture in database.architectures[:10]:
        title = architecture.name.strip()
        if not title:
            continue
        evidence_ids = architecture.evidence_ids or source_evidence_ids[:5]
        artifacts.append(Artifact(
            id=f"ART-V1-ARCH-CARD-{uuid4().hex[:8]}",
            project_id=project.id,
            artifact_type=ArtifactType.PLAYER_TOOL_MAP,
            title=title,
            content_path=f"architectures/{_obsidian_filename(title)}.md",
            content=_render_architecture_card(project, architecture, database, evidence_ids),
            source_evidence_ids=evidence_ids,
            schema_version="v1-card",
            created_at=created_at,
        ))
    for tool in database.tools[:16]:
        title = tool.name.strip()
        if not title:
            continue
        evidence_ids = tool.evidence_ids or source_evidence_ids[:5]
        artifacts.append(Artifact(
            id=f"ART-V1-TOOL-CARD-{uuid4().hex[:8]}",
            project_id=project.id,
            artifact_type=ArtifactType.PLAYER_TOOL_MAP,
            title=title,
            content_path=f"tools/{_obsidian_filename(title)}.md",
            content=_render_tool_card(project, tool, database, evidence_ids),
            source_evidence_ids=evidence_ids,
            schema_version="v1-card",
            created_at=created_at,
        ))
    for index, question in enumerate(database.open_questions[:12], start=1):
        title = _question_card_title(index, question)
        artifacts.append(Artifact(
            id=f"ART-V1-QUESTION-CARD-{uuid4().hex[:8]}",
            project_id=project.id,
            artifact_type=ArtifactType.UNRESOLVED_QUESTIONS,
            title=title,
            content_path=f"questions/{_obsidian_filename(title)}.md",
            content=_render_question_card(project, title, question, database, source_evidence_ids[:5]),
            source_evidence_ids=source_evidence_ids[:5],
            schema_version="v1-card",
            created_at=created_at,
        ))
    return artifacts


def _render_concept_card(project: ResearchProject, concept: DomainConcept, evidence_ids: list[str]) -> str:
    related_links = [_wikilink(name) for name in concept.related if name.strip()]
    return (
        f"# {concept.name}\n\n"
        f"> 类型：概念卡｜领域：{project.domain}\n\n"
        "## 定义\n\n"
        f"{concept.definition}\n\n"
        "## 为什么重要\n\n"
        f"{concept.why_it_matters}\n\n"
        "## 新手理解\n\n"
        "把这张卡当作学习入口：先确认它解决什么问题，再看它和哪些架构、工具或场景相连。"
        "如果暂时没有足够证据，应在下一轮补库时补充官方文档、论文、工程案例或招聘 JD。\n\n"
        "## 关联\n\n"
        f"{_join_or_placeholder(related_links)}\n\n"
        "## 证据\n\n"
        f"{_join_or_placeholder(evidence_ids)}\n"
    )


def _render_architecture_card(
    project: ResearchProject,
    architecture: DomainArchitecture,
    database: DomainKnowledgeBase,
    evidence_ids: list[str],
) -> str:
    concept_links = [_wikilink(concept.name) for concept in database.concepts[:6]]
    tool_links = [_wikilink(tool.name) for tool in database.tools[:6]]
    return (
        f"# {architecture.name}\n\n"
        f"> 类型：架构卡｜领域：{project.domain}\n\n"
        "## 核心说明\n\n"
        f"{architecture.summary}\n\n"
        "## 适用场景\n\n"
        f"{_bullet_lines(architecture.use_cases)}\n\n"
        "## 优势\n\n"
        f"{_bullet_lines(architecture.strengths)}\n\n"
        "## 局限与失败模式\n\n"
        f"{_bullet_lines(architecture.limitations)}\n\n"
        "## 关联概念与工具\n\n"
        f"- 概念：{_join_or_placeholder(concept_links)}\n"
        f"- 工具：{_join_or_placeholder(tool_links)}\n\n"
        "## 证据\n\n"
        f"{_join_or_placeholder(evidence_ids)}\n"
    )


def _render_tool_card(
    project: ResearchProject,
    tool: DomainTool,
    database: DomainKnowledgeBase,
    evidence_ids: list[str],
) -> str:
    architecture_links = [_wikilink(item.name) for item in database.architectures[:6]]
    return (
        f"# {tool.name}\n\n"
        f"> 类型：工具卡｜领域：{project.domain}\n\n"
        f"- 分类：{tool.category}\n"
        f"- 用途：{tool.use_case}\n"
        f"- 取舍：{tool.tradeoffs}\n\n"
        "## 什么时候应该关注它\n\n"
        "当你已经理解相关概念，并需要把知识落到一个可运行的小项目时，再深入研究这个工具。"
        "优先记录它解决的问题、上手成本、生产风险和替代方案。\n\n"
        "## 关联架构\n\n"
        f"{_join_or_placeholder(architecture_links)}\n\n"
        "## 证据\n\n"
        f"{_join_or_placeholder(evidence_ids)}\n"
    )


def _render_question_card(
    project: ResearchProject,
    title: str,
    question: str,
    database: DomainKnowledgeBase,
    evidence_ids: list[str],
) -> str:
    concept_links = [_wikilink(concept.name) for concept in database.concepts[:6]]
    return (
        f"# {title}\n\n"
        f"> 类型：待验证问题｜领域：{project.domain}\n\n"
        f"## 问题\n\n{question}\n\n"
        "## 为什么值得继续查\n\n"
        "这类问题决定知识库是否只是资料堆积，还是能够支持判断。下一轮应该优先寻找更高质量来源，"
        "并记录支持证据、反证证据和仍然不确定的边界。\n\n"
        "## 下一步搜索方向\n\n"
        f"- 围绕问题关键词继续搜索：{question}\n"
        f"- 回看相关概念：{_join_or_placeholder(concept_links)}\n"
        "- 优先补充官方文档、论文、权威媒体、招聘 JD、工程案例或带来源的外部 AI Deep Search 报告。\n\n"
        "## 当前证据\n\n"
        f"{_join_or_placeholder(evidence_ids)}\n"
    )


def _render_domain_overview(
    project: ResearchProject,
    database: DomainKnowledgeBase,
    source_evidence_ids: list[str],
) -> str:
    concept_names = "、".join(_wikilink(concept.name) for concept in database.concepts[:6])
    architecture_names = "、".join(_wikilink(item.name) for item in database.architectures[:5])
    tool_names = "、".join(_wikilink(tool.name) for tool in database.tools[:6])
    evidence_line = "、".join(source_evidence_ids[:8]) or "暂无证据"
    return (
        f"# {project.domain} 领域总览\n\n"
        f"{database.overview}\n\n"
        "## 怎么使用这个知识库\n\n"
        "这不是一次性行业报告，而是一个可以继续填充的学习型知识库。建议先读领域总览，"
        "再按入门路线学习核心概念、主流架构和工具框架，最后把待验证问题变成下一轮搜索任务。\n\n"
        "## 核心概念速览\n\n"
        f"{concept_names or '暂无概念'}\n\n"
        "## 主流架构速览\n\n"
        f"{architecture_names or '暂无架构'}\n\n"
        "## 工具与框架速览\n\n"
        f"{tool_names or '暂无工具'}\n\n"
        "## 当前证据范围\n\n"
        f"本轮知识库引用证据：{evidence_line}。所有未被证据充分支撑的判断都应继续标记为待验证。"
    )


def _render_learning_path(project: ResearchProject, database: DomainKnowledgeBase) -> str:
    lines = [
        f"# {project.domain} 入门路线",
        "",
        "这条路线面向“快速理解陌生领域”，不是创业竞品分析，也不是内容运营分析。",
        "",
        "## 学习路径",
        "",
    ]
    for index, step in enumerate(database.learning_path, start=1):
        lines.append(f"### {index}. {step}")
        lines.append("")
        lines.append(f"- 学习目标：理解这一步对应的概念、架构或工具，并能用自己的话复述。")
        lines.append("- 实践动作：找一个最小例子，记录它的输入、处理过程、输出和失败情况。")
        lines.append("- Obsidian 卡片：为这一步新建一张卡片，至少包含“定义 / 例子 / 关联概念 / 证据链接”。")
        lines.append(f"- 完成标志：能把这一步沉淀成一张 Obsidian 卡片，并链接至少一个相关概念或证据。")
        lines.append("- 常见误区：不要只收藏链接或框架名，要写清楚它解决的问题和不适合的场景。")
        lines.append("")
    lines.extend([
        "## 建议节奏",
        "",
        "- 第一轮只求建立全局地图，不追求所有细节一次学完。",
        "- 第二轮围绕不理解的概念补资料，并把证据补回 `_sources/evidence-ledger.md`。",
        "- 第三轮选择一个最小项目验证架构，例如工具调用、RAG Agent 或工作流 Agent。",
    ])
    return "\n".join(lines)


def _render_core_concepts(database: DomainKnowledgeBase) -> str:
    lines = ["# 核心概念", ""]
    for concept in database.concepts:
        lines.extend([
            f"## {_wikilink(concept.name)}",
            "",
            f"**定义**：{concept.definition}",
            "",
            f"**为什么重要**：{concept.why_it_matters}",
            "",
            f"**相关概念**：{_join_or_placeholder([_wikilink(name) for name in concept.related])}",
            "",
            f"**证据**：{_join_or_placeholder(concept.evidence_ids)}",
            "",
        ])
    return "\n".join(lines).strip()


def _render_architecture_tool_map(database: DomainKnowledgeBase) -> str:
    lines = ["# 主流架构与工具地图", ""]
    lines.append("## 主流架构")
    lines.append("")
    for architecture in database.architectures:
        lines.extend([
            f"### {_wikilink(architecture.name)}",
            "",
            architecture.summary,
            "",
            f"- 适用场景：{_join_or_placeholder(architecture.use_cases)}",
            f"- 优势：{_join_or_placeholder(architecture.strengths)}",
            f"- 局限：{_join_or_placeholder(architecture.limitations)}",
            f"- 证据：{_join_or_placeholder(architecture.evidence_ids)}",
            "",
        ])
    lines.append("## 工具与框架")
    lines.append("")
    for tool in database.tools:
        lines.extend([
            f"### {_wikilink(tool.name)}",
            "",
            f"- 类型：{tool.category}",
            f"- 用途：{tool.use_case}",
            f"- 取舍：{tool.tradeoffs}",
            f"- 证据：{_join_or_placeholder(tool.evidence_ids)}",
            "",
        ])
    return "\n".join(lines).strip()


def _render_trends(database: DomainKnowledgeBase) -> str:
    lines = ["# 趋势与证据", ""]
    for trend in database.trends:
        lines.append(f"- {trend}")
    lines.extend([
        "",
        "## 如何继续验证",
        "",
        "把每条趋势拆成可搜索的问题：谁提出了这个趋势？有哪些项目或论文支撑？有没有反例？"
        "下一轮搜索应优先补充原始论文、官方文档、工程案例和评测基准。",
    ])
    return "\n".join(lines)


def _render_problem_opportunities(project: ResearchProject, database: DomainKnowledgeBase) -> str:
    architecture_names = "、".join(item.name for item in database.architectures)
    tool_names = "、".join(tool.name for tool in database.tools)
    return (
        f"# {project.domain} 问题与机会\n\n"
        "这里的“机会”不是商业创业机会，而是学习和建库时下一步最值得补齐的认知缺口。\n\n"
        "## 当前主要问题\n\n"
        f"- 概念容易混用：需要区分 {_join_or_placeholder([_wikilink(concept.name) for concept in database.concepts[:5]])}。\n"
        f"- 架构选择困难：需要比较 {_join_or_placeholder([_wikilink(item.name) for item in database.architectures]) if database.architectures else architecture_names or '不同 Agent 架构'} 的适用边界。\n"
        f"- 工具框架很多：需要理解 {_join_or_placeholder([_wikilink(tool.name) for tool in database.tools]) if database.tools else tool_names or '主流框架'} 的取舍，而不是只看热度。\n\n"
        "## 下一步补库机会\n\n"
        "- 为每个核心概念补一张概念卡：定义、例子、反例、相关工具、证据。\n"
        "- 为每个主流架构补一张架构卡：流程图、适用场景、失败模式、代表框架。\n"
        "- 为每个工具补一张工具卡：定位、上手成本、生产风险、替代品。\n"
    )


def _render_open_questions(database: DomainKnowledgeBase) -> str:
    lines = ["# 待验证问题", ""]
    for index, question in enumerate(database.open_questions, start=1):
        lines.extend([
            f"## {_wikilink(_question_card_title(index, question))}",
            "",
            f"原始问题：{question}",
            "",
            "- 当前状态：待验证。",
            "- 下一步：补充至少两个来源，并记录支持或反驳证据。",
            "",
        ])
    return "\n".join(lines).strip()


def _obsidian_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\n\r\t]+', "-", value).strip(" .-")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    return cleaned[:80].strip() or "未命名卡片"


def _wikilink(value: str) -> str:
    title = value.strip()
    return f"[[{title}]]" if title else "[[未命名卡片]]"


def _bullet_lines(values: list[str]) -> str:
    filtered = [value.strip() for value in values if value.strip()]
    if not filtered:
        return "- 待补充"
    return "\n".join(f"- {value}" for value in filtered)


def _question_card_title(index: int, question: str) -> str:
    cleaned = re.sub(r"[？?。.!！]+$", "", question.strip())
    cleaned = _truncate_text(cleaned, 48)
    return f"待验证问题 {index} - {cleaned or '继续补证'}"


def _join_or_placeholder(values: list[str], placeholder: str = "待补充") -> str:
    return "、".join(value for value in values if value) or placeholder


def _evidence_brief(evidence: list[EvidenceItem]) -> str:
    if not evidence:
        return "暂无外部证据。"
    return "\n".join(
        f"- [{item.id}] {item.source_title}: {_clean_search_snippet(item.snippet, fallback=item.source_title)} ({item.source_url or 'no url'})"
        for item in evidence[:12]
    )


def _evidence_lines(evidence: list[EvidenceItem]) -> str:
    if not evidence:
        return "- 暂无外部证据；以下内容只能作为待验证研究框架。"
    return "\n".join(
        f"- [{item.source_title}]({item.source_url})：{_clean_search_snippet(item.snippet, fallback=item.source_title)}"
        if item.source_url
        else f"- {item.source_title}：{_clean_search_snippet(item.snippet, fallback=item.source_title)}"
        for item in evidence[:12]
    )


def _markdown_from_value(value: str | list[Any]) -> str:
    if isinstance(value, list):
        return "\n".join(f"{index}. {_section_to_markdown(item)}" for index, item in enumerate(value, start=1))
    return value


def _section_to_markdown(value: Any) -> str:
    if isinstance(value, dict):
        title = str(value.get("title") or value.get("name") or "").strip()
        content = str(value.get("content") or value.get("summary") or value.get("text") or "").strip()
        if title and content:
            return f"{title}：{content}"
        return title or content or str(value)
    return str(value)
