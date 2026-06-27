"""Simplified runnable V1 knowledge-system pipeline."""

from __future__ import annotations

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


_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\([^)]+\)")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)]\([^)]+\)")
_RAW_URL_RE = re.compile(r"https?://\S+")
_WHITESPACE_RE = re.compile(r"\s+")
_V1_SNIPPET_MAX_CHARS = 420
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

    await emit_event(RunEvent(
        event_type="node_started",
        gate="source_collection",
        agent="Search Scout",
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
        v1_blocked_domains = list(dict.fromkeys(blocked_domains + list(_V1_BLOCKED_DOMAINS)))
        search_query = _build_v1_search_query(project.domain)
        results = await search_provider.search(SearchQuery(
            query=search_query,
            market_scope=project.market_scope.value,
            max_results=8,
            allowed_domains=allowed_domains,
            blocked_domains=v1_blocked_domains,
        ))
        results = _filter_v1_search_results(results, project=project)
        if (
            not results
            and project.source_policy == SourcePolicy.RELIABLE_FIRST
            and allowed_domains
        ):
            await emit_event(RunEvent(
                event_type="node_degraded",
                gate="source_collection",
                agent="Search Scout",
                message="可靠优先来源暂未命中，已降级补充开放网络搜索",
                progress_current=1,
                progress_total=3,
                severity="warning",
            ))
            results = await search_provider.search(SearchQuery(
                query=search_query,
                market_scope=project.market_scope.value,
                max_results=8,
                allowed_domains=[],
                blocked_domains=v1_blocked_domains,
            ))
            results = _filter_v1_search_results(results, project=project)
        for index, result in enumerate(results, start=1):
            item = _search_result_to_evidence(project, result, index)
            repository.add_evidence(item)
            evidence.append(item)
            await emit_event(RunEvent(
                event_type="evidence_collected",
                gate="source_collection",
                agent="Search Scout",
                message=f"已记录来源：{result.title}",
                data={"evidence_id": item.id, "url": result.url},
            ))

    await emit_event(RunEvent(
        event_type="node_completed",
        gate="source_collection",
        agent="Search Scout",
        message=f"资料收集完成，当前证据 {len(evidence)} 条",
        progress_current=1,
        progress_total=3,
    ))
    await emit_event(RunEvent(
        event_type="node_started",
        gate="knowledge_structuring",
        agent="Knowledge Builder",
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
    return (
        f"{domain_text} 最新趋势 核心框架 主要工具 玩家格局 "
        "production adoption evaluation challenges 2026"
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

    tokens = [
        token
        for token in re.split(r"[\s,，;；/|]+", domain_text)
        if len(token) >= 2
    ]
    if not tokens:
        return True
    return any(token in text for token in tokens[:4])


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
