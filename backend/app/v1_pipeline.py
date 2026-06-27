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

    database = await _build_knowledge_database(
        project=project,
        evidence=evidence,
        llm_provider=llm_provider,
    )
    source_evidence_ids = [item.id for item in evidence]
    artifacts = _build_artifacts(project, database, source_evidence_ids)
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
    if "大模型" in domain_text or "llm" in domain_text.lower():
        return (
            f"{domain_text} 大模型应用开发 岗位 技能要求 RAG Agent "
            "模型API Python LangChain LangGraph 就业方向 2026"
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
    if "大模型" in domain_text or "llm" in domain_text:
        model_markers = ("大模型", "llm", "large model", "模型api", "模型 api", "rag", "agent")
        career_markers = ("就业", "岗位", "招聘", "职业", "技能", "薪", "工程师", "开发")
        return any(marker in text for marker in model_markers) and any(marker in text for marker in career_markers)

    tokens = _topic_tokens(domain_text)
    if not tokens:
        return True
    return any(token in text for token in tokens[:4])


def _topic_tokens(domain_text: str) -> list[str]:
    split_tokens = [
        token
        for token in re.split(r"[\s,，;；/|]+", domain_text)
        if len(token) >= 2
    ]
    if split_tokens:
        tokens = split_tokens
    else:
        tokens = [domain_text]
    chinese_markers = ("大模型", "开发", "就业", "岗位", "职业", "架构", "工具", "框架", "智能体", "应用")
    tokens.extend(marker for marker in chinese_markers if marker in domain_text)
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


async def _build_knowledge_database(
    *,
    project: ResearchProject,
    evidence: list[EvidenceItem],
    llm_provider: LLMProvider | None,
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
        generated = await llm_provider.complete_structured(
            [ChatMessage(role="user", content=prompt)],
            DomainKnowledgeBase,
        )
    except Exception:
        return fallback
    if not isinstance(generated, DomainKnowledgeBase):
        return fallback
    return _merge_database_with_fallback(generated, fallback)


def _fallback_database(project: ResearchProject, evidence: list[EvidenceItem]) -> DomainKnowledgeBase:
    evidence_ids = [item.id for item in evidence] or ["待补充证据"]
    topic = project.domain
    evidence_themes = _evidence_theme_lines(evidence)
    if "大模型" in topic or "llm" in topic.lower():
        return _large_model_career_database(project, evidence, evidence_ids, evidence_themes)
    return DomainKnowledgeBase(
        overview=(
            f"{topic} 知识库用于先抹平信息差：建立术语、主流架构、工具框架、趋势和待验证问题。"
            f"当前版本基于 {len(evidence)} 条搜索证据生成，适合作为继续补资料的 Obsidian 起点。"
            f"{' 证据主题包括：' + evidence_themes if evidence_themes else ''}"
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
                definition="模型通过函数、API、MCP Server 或浏览器等外部能力完成实际动作。",
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


def _build_artifacts(
    project: ResearchProject,
    database: DomainKnowledgeBase,
    source_evidence_ids: list[str],
) -> list[Artifact]:
    now = datetime.now(UTC)
    specs = [
        (ArtifactType.DOMAIN_OVERVIEW, "领域总览", "00-领域总览.md", _render_domain_overview(project, database, source_evidence_ids)),
        (ArtifactType.LEARNING_PATH, "入门路线", "01-入门路线.md", _render_learning_path(project, database)),
        (ArtifactType.CORE_CONCEPTS, "核心概念", "02-核心概念.md", _render_core_concepts(database)),
        (ArtifactType.PLAYER_TOOL_MAP, "主流架构与工具地图", "03-玩家与工具地图.md", _render_architecture_tool_map(database)),
        (ArtifactType.TREND_EVIDENCE, "趋势与证据", "04-趋势与证据.md", _render_trends(database)),
        (ArtifactType.PROBLEM_OPPORTUNITY_MAP, "问题与机会", "05-问题与机会.md", _render_problem_opportunities(project, database)),
        (ArtifactType.UNRESOLVED_QUESTIONS, "待验证问题", "99-待验证问题.md", _render_open_questions(database)),
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


def _render_domain_overview(
    project: ResearchProject,
    database: DomainKnowledgeBase,
    source_evidence_ids: list[str],
) -> str:
    concept_names = "、".join(concept.name for concept in database.concepts[:6])
    architecture_names = "、".join(item.name for item in database.architectures[:5])
    tool_names = "、".join(tool.name for tool in database.tools[:6])
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
            f"## {concept.name}",
            "",
            f"**定义**：{concept.definition}",
            "",
            f"**为什么重要**：{concept.why_it_matters}",
            "",
            f"**相关概念**：{_join_or_placeholder(concept.related)}",
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
            f"### {architecture.name}",
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
            f"### {tool.name}",
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
        f"- 概念容易混用：需要区分 {_join_or_placeholder([concept.name for concept in database.concepts[:5]])}。\n"
        f"- 架构选择困难：需要比较 {architecture_names or '不同 Agent 架构'} 的适用边界。\n"
        f"- 工具框架很多：需要理解 {tool_names or '主流框架'} 的取舍，而不是只看热度。\n\n"
        "## 下一步补库机会\n\n"
        "- 为每个核心概念补一张概念卡：定义、例子、反例、相关工具、证据。\n"
        "- 为每个主流架构补一张架构卡：流程图、适用场景、失败模式、代表框架。\n"
        "- 为每个工具补一张工具卡：定位、上手成本、生产风险、替代品。\n"
    )


def _render_open_questions(database: DomainKnowledgeBase) -> str:
    lines = ["# 待验证问题", ""]
    for question in database.open_questions:
        lines.extend([
            f"## {question}",
            "",
            "- 当前状态：待验证。",
            "- 下一步：补充至少两个来源，并记录支持或反驳证据。",
            "",
        ])
    return "\n".join(lines).strip()


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
