"""Simplified runnable V1 knowledge-system pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
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
    learning_path: str | list[str] = ""
    core_concepts: str = ""
    player_tool_map: str = ""
    trend_evidence: str = ""
    problem_opportunity_map: str = ""
    unresolved_questions: str = ""
    title: str | None = None
    content: str | None = None
    sections: list[str] = Field(default_factory=list)


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

    await emit_event(RunEvent(
        event_type="node_started",
        gate="source_collection",
        message="开始收集 V1 领域资料",
        progress_current=1,
        progress_total=3,
    ))

    evidence = list(repository.list_evidence(project.id))
    if project.source_policy != SourcePolicy.USER_MATERIALS_ONLY and search_provider is not None:
        allowed_domains, blocked_domains = search_constraints_for_policy(
            {
                "market_scope": project.market_scope.value,
                "source_policy": project.source_policy.value,
            },
            verification=project.source_policy == SourcePolicy.RELIABLE_ONLY,
        )
        results = await search_provider.search(SearchQuery(
            query=f"{project.domain} domain overview trends players tools problems opportunities",
            market_scope=project.market_scope.value,
            max_results=5,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        ))
        for index, result in enumerate(results, start=1):
            item = _search_result_to_evidence(project, result, index)
            repository.add_evidence(item)
            evidence.append(item)
            await emit_event(RunEvent(
                event_type="evidence_collected",
                gate="source_collection",
                message=f"已记录来源：{result.title}",
                data={"evidence_id": item.id, "url": result.url},
            ))

    await emit_event(RunEvent(
        event_type="node_completed",
        gate="source_collection",
        message=f"资料收集完成，当前证据 {len(evidence)} 条",
        progress_current=1,
        progress_total=3,
    ))
    await emit_event(RunEvent(
        event_type="node_started",
        gate="knowledge_structuring",
        message="开始生成 V1 知识系统",
        progress_current=2,
        progress_total=3,
    ))

    content = await _build_knowledge_content(
        project=project,
        evidence=evidence,
        llm_provider=llm_provider,
    )
    source_evidence_ids = [item.id for item in evidence]
    artifacts = _build_artifacts(project, content, source_evidence_ids)
    for artifact in artifacts:
        repository.add_artifact(artifact)

    await emit_event(RunEvent(
        event_type="node_completed",
        gate="knowledge_structuring",
        message="V1 知识系统生成完成",
        progress_current=2,
        progress_total=3,
    ))
    await emit_event(RunEvent(
        event_type="node_completed",
        gate="obsidian_export",
        message="V1 Markdown 产物已写入项目",
        progress_current=3,
        progress_total=3,
    ))
    return artifacts


def _search_result_to_evidence(project: ResearchProject, result: SearchResult, index: int) -> EvidenceItem:
    evidence_id = f"EV-V1-{project.id}-{index}"
    return EvidenceItem(
        id=evidence_id,
        project_id=project.id,
        source_title=result.title,
        source_url=result.url,
        source_type="web",
        source_channel=SourceChannel.SEARCH,
        source_policy=project.source_policy.value,
        raw_excerpt=result.snippet,
        snippet=result.snippet,
        summary=result.snippet,
        claims=[
            EvidenceClaim(
                claim_id=f"{evidence_id}-CLAIM-1",
                text=result.snippet,
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
    generated = await llm_provider.complete_structured(
        [ChatMessage(role="user", content=prompt)],
        V1KnowledgeContent,
    )
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
    sections = "\n".join(f"- {item}" for item in generated.sections)
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


def _build_artifacts(
    project: ResearchProject,
    content: V1KnowledgeContent,
    source_evidence_ids: list[str],
) -> list[Artifact]:
    now = datetime.now(UTC)
    specs = [
        (ArtifactType.DOMAIN_OVERVIEW, "领域总览", "00-领域总览.md", content.domain_overview),
        (ArtifactType.LEARNING_PATH, "入门路线", "01-入门路线.md", _markdown_from_value(content.learning_path)),
        (ArtifactType.CORE_CONCEPTS, "核心概念", "02-核心概念.md", content.core_concepts),
        (ArtifactType.PLAYER_TOOL_MAP, "玩家与工具地图", "03-玩家与工具地图.md", content.player_tool_map),
        (ArtifactType.TREND_EVIDENCE, "趋势与证据", "04-趋势与证据.md", content.trend_evidence),
        (ArtifactType.PROBLEM_OPPORTUNITY_MAP, "问题与机会", "05-问题与机会.md", content.problem_opportunity_map),
        (ArtifactType.UNRESOLVED_QUESTIONS, "待验证问题", "99-待验证问题.md", content.unresolved_questions),
    ]
    return [
        Artifact(
            id=f"ART-V1-{artifact_type.value.upper()}-{uuid4().hex[:8]}",
            project_id=project.id,
            artifact_type=artifact_type,
            title=title,
            content_path=content_path,
            content=markdown,
            source_evidence_ids=source_evidence_ids,
            schema_version="v1",
            created_at=now,
        )
        for artifact_type, title, content_path, markdown in specs
    ]


def _evidence_brief(evidence: list[EvidenceItem]) -> str:
    if not evidence:
        return "暂无外部证据。"
    return "\n".join(
        f"- [{item.id}] {item.source_title}: {item.snippet} ({item.source_url or 'no url'})"
        for item in evidence[:12]
    )


def _evidence_lines(evidence: list[EvidenceItem]) -> str:
    if not evidence:
        return "- 暂无外部证据；以下内容只能作为待验证研究框架。"
    return "\n".join(
        f"- [{item.source_title}]({item.source_url})：{item.snippet}"
        if item.source_url
        else f"- {item.source_title}：{item.snippet}"
        for item in evidence[:12]
    )


def _markdown_from_value(value: str | list[str]) -> str:
    if isinstance(value, list):
        return "\n".join(f"{index}. {item}" for index, item in enumerate(value, start=1))
    return value
