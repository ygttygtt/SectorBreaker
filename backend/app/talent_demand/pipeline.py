"""Runnable talent-demand intelligence pipeline."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from uuid import uuid4

from backend.app.providers.interfaces import (
    ChatMessage,
    JobPostingSource,
    JobSourceProvider,
    JobSourceQuery,
    LLMProvider,
    SearchProvider,
    SearchQuery,
)
from backend.app.schemas import (
    Artifact,
    ClaimStrength,
    ClaimType,
    EvidenceClaim,
    EvidenceItem,
    ResearchProject,
    RunEvent,
    SourceChannel,
    SourceQuality,
    SourceType,
    VerificationStatus,
)
from backend.app.storage.sqlite import SQLiteRepository
from backend.app.talent_demand.export import build_talent_demand_artifacts
from backend.app.talent_demand.extraction import extract_job_posting_signals_from_text
from backend.app.talent_demand.models import JobPostingSignal, TalentDemandKnowledgeBase
from backend.app.talent_demand.skills import build_skill_matrix
from backend.app.talent_demand.source_coverage import build_source_coverage_matrix

_MIN_TALENT_EVIDENCE = 5


async def run_talent_demand_pipeline(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    job_source_provider: JobSourceProvider | None = None,
    job_source_query: JobSourceQuery | None = None,
    emit: Callable[[RunEvent], Awaitable[None]] | None = None,
) -> list[Artifact]:
    """Run the V1.3 talent-demand mode and persist evidence plus artifacts."""

    async def emit_event(event: RunEvent) -> None:
        if emit is not None:
            await emit(event)

    await emit_event(RunEvent(
        event_type="node_started",
        gate="talent_source_intake",
        agent="Talent Source Scout",
        message="开始收集人才需求材料：优先读取上传 JD/报告，搜索作为补充",
        progress_current=1,
        progress_total=7,
    ))

    evidence = repository.list_evidence(project.id)
    await _persist_document_evidence(project, repository, evidence, emit_event)
    if job_source_provider is not None and job_source_query is not None:
        await _persist_job_source_evidence(
            project,
            repository,
            evidence,
            job_source_provider,
            job_source_query,
            emit_event,
        )
    if len(evidence) < _MIN_TALENT_EVIDENCE and search_provider is not None:
        await _persist_search_evidence(project, repository, evidence, search_provider, emit_event)

    await emit_event(RunEvent(
        event_type="node_completed",
        gate="talent_source_intake",
        agent="Talent Source Scout",
        message=f"人才需求材料收集完成，当前证据 {len(evidence)} 条",
        progress_current=1,
        progress_total=7,
        data={"evidence_count": len(evidence)},
    ))

    await emit_event(RunEvent(
        event_type="node_started",
        gate="jd_signal_extraction",
        agent="JD Extractor",
        message="正在抽取岗位、公司、薪资、经验、职责和技能信号",
        progress_current=2,
        progress_total=7,
    ))
    postings = _extract_postings(evidence, project)
    await emit_event(RunEvent(
        event_type="node_completed",
        gate="jd_signal_extraction",
        agent="JD Extractor",
        message=f"岗位信号抽取完成：{len(postings)} 条岗位样本",
        progress_current=2,
        progress_total=7,
        data={"posting_count": len(postings)},
    ))

    await emit_event(RunEvent(
        event_type="node_started",
        gate="skill_normalization",
        agent="Skill Normalizer",
        message="正在归一化技能别名并生成技能需求矩阵",
        progress_current=3,
        progress_total=7,
    ))
    skill_matrix = build_skill_matrix(postings)
    await emit_event(RunEvent(
        event_type="node_completed",
        gate="skill_normalization",
        agent="Skill Normalizer",
        message=f"技能需求矩阵生成完成：{len(skill_matrix)} 个技能节点",
        progress_current=3,
        progress_total=7,
        data={"skill_count": len(skill_matrix)},
    ))

    await emit_event(RunEvent(
        event_type="node_started",
        gate="source_coverage",
        agent="Source Coverage",
        message="正在检查样本量、信源结构、薪资/经验/技能覆盖",
        progress_current=4,
        progress_total=7,
    ))
    coverage = build_source_coverage_matrix(evidence, postings, min_posting_sample=_MIN_TALENT_EVIDENCE)
    await emit_event(RunEvent(
        event_type="node_completed",
        gate="source_coverage",
        agent="Source Coverage",
        message=f"信源覆盖检查完成：{coverage.total_evidence} 条证据，{len(coverage.gaps)} 个待补缺口",
        progress_current=4,
        progress_total=7,
        severity="warning" if coverage.gaps else "info",
        data=coverage.model_dump(mode="json"),
    ))

    await emit_event(RunEvent(
        event_type="node_started",
        gate="talent_synthesis",
        agent="Talent Analyst",
        message="正在生成岗位需求知识库、能力模型和学习路径",
        progress_current=5,
        progress_total=7,
    ))
    knowledge_base = await _build_knowledge_base(
        project=project,
        postings=postings,
        skill_matrix=skill_matrix,
        evidence=evidence,
        llm_provider=llm_provider,
    )
    knowledge_base.source_coverage = coverage
    await emit_event(RunEvent(
        event_type="node_completed",
        gate="talent_synthesis",
        agent="Talent Analyst",
        message="人才需求知识库生成完成",
        progress_current=5,
        progress_total=7,
    ))

    await emit_event(RunEvent(
        event_type="node_started",
        gate="artifact_review",
        agent="Artifact Reviewer",
        message="正在检查人才需求产物是否详实、是否标注样本限制",
        progress_current=6,
        progress_total=7,
    ))
    knowledge_base = _review_and_expand_knowledge_base(knowledge_base, project)
    await emit_event(RunEvent(
        event_type="node_completed",
        gate="artifact_review",
        agent="Artifact Reviewer",
        message="人才需求产物检查完成",
        progress_current=6,
        progress_total=7,
    ))

    await emit_event(RunEvent(
        event_type="node_started",
        gate="obsidian_export",
        agent="Export Writer",
        message="正在写入人才需求 Obsidian vault 产物",
        progress_current=7,
        progress_total=7,
    ))
    artifacts = build_talent_demand_artifacts(project=project, knowledge_base=knowledge_base)
    for artifact in artifacts:
        repository.add_artifact(artifact)
    await emit_event(RunEvent(
        event_type="node_completed",
        gate="obsidian_export",
        agent="Export Writer",
        message=f"人才需求 Markdown 产物已写入项目：{len(artifacts)} 个文件",
        progress_current=7,
        progress_total=7,
        data={"artifact_count": len(artifacts), "source_coverage": coverage.model_dump(mode="json")},
    ))
    return artifacts


async def _persist_document_evidence(
    project: ResearchProject,
    repository: SQLiteRepository,
    evidence: list[EvidenceItem],
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> None:
    seen_ids = {item.id for item in evidence}
    for index, document in enumerate(repository.list_documents(project.id), start=1):
        evidence_id = f"EV-TALENT-DOC-{document.id}"
        if evidence_id in seen_ids:
            continue
        channel = SourceChannel.ASSISTANT_BRIEF if document.channel == "assistant_brief" else SourceChannel.USER_UPLOAD
        item = EvidenceItem(
            id=evidence_id,
            project_id=project.id,
            source_title=document.file_name or f"上传材料 {index}",
            source_url=None,
            source_type=SourceType.ASSISTANT_BRIEF.value if channel == SourceChannel.ASSISTANT_BRIEF else SourceType.USER_MATERIAL.value,
            source_channel=channel,
            source_policy=project.source_policy.value,
            raw_excerpt=document.content,
            snippet=_shorten(document.content, 480),
            summary=_shorten(document.content, 480),
            claims=[EvidenceClaim(
                claim_id=f"{evidence_id}-CLAIM-1",
                text=_shorten(document.content, 240),
                claim_type=ClaimType.GENERAL_FACT,
                support_level=0.55,
                requires_verification=channel == SourceChannel.ASSISTANT_BRIEF,
                verification_status=VerificationStatus.PARTIALLY_VERIFIED,
                evidence_ids=[evidence_id],
                notes="人才需求模式上传材料，作为岗位/JD/报告信号来源。",
            )],
            source_quality=SourceQuality.MEDIUM if channel == SourceChannel.USER_UPLOAD else SourceQuality.LOW,
            claim_strength=ClaimStrength.OPINION,
            bias_risk="上传材料可能存在样本偏差，需要结合更多 JD 或搜索来源交叉验证。",
            needs_counterevidence=channel == SourceChannel.ASSISTANT_BRIEF,
            collected_by="talent_demand_document_intake",
            confidence=0.65 if channel == SourceChannel.USER_UPLOAD else 0.45,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        )
        repository.add_evidence(item)
        evidence.append(item)
        seen_ids.add(item.id)
        await emit_event(RunEvent(
            event_type="evidence_collected",
            gate="talent_source_intake",
            agent="Talent Source Scout",
            message=f"已读取上传材料：{item.source_title}",
            data={"evidence_id": item.id, "source_channel": item.source_channel.value},
        ))


async def _persist_job_source_evidence(
    project: ResearchProject,
    repository: SQLiteRepository,
    evidence: list[EvidenceItem],
    job_source_provider: JobSourceProvider,
    query: JobSourceQuery,
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> None:
    await emit_event(RunEvent(
        event_type="node_started",
        gate="boss_job_intake",
        agent="Boss Job Source",
        message=f"正在采集 Boss 职位样本：{query.keyword} / {query.city or '不限城市'}",
        progress_current=1,
        progress_total=7,
    ))
    status = await job_source_provider.status()
    if not status.available:
        await emit_event(RunEvent(
            event_type="node_degraded",
            gate="boss_job_intake",
            agent="Boss Job Source",
            message=status.message,
            severity="warning",
            data={
                "provider": status.provider,
                "configured": status.configured,
                "available": status.available,
                "diagnostics": status.diagnostics or [],
            },
        ))
        return

    jobs = await job_source_provider.search_jobs(query)
    seen_keys = {
        _job_dedupe_key_from_evidence(item)
        for item in evidence
        if item.source_channel == SourceChannel.BOSS_JOB
    }
    created = 0
    for job in jobs:
        key = _job_dedupe_key(job)
        if key in seen_keys:
            continue
        evidence_id = f"EV-TALENT-BOSS-{project.id}-{len(evidence) + 1}"
        text = _job_to_evidence_text(job)
        item = EvidenceItem(
            id=evidence_id,
            project_id=project.id,
            source_title=_job_title(job),
            source_url=job.url,
            source_type=SourceType.WEB.value,
            source_channel=SourceChannel.BOSS_JOB,
            source_policy=project.source_policy.value,
            raw_excerpt=text,
            snippet=_shorten(text, 520),
            summary=_shorten(text, 520),
            claims=[EvidenceClaim(
                claim_id=f"{evidence_id}-CLAIM-1",
                text=_shorten(text, 280),
                claim_type=ClaimType.GENERAL_FACT,
                support_level=0.62,
                requires_verification=False,
                verification_status=VerificationStatus.PARTIALLY_VERIFIED,
                evidence_ids=[evidence_id],
                notes="Boss 职位样本来自本地招聘信源适配器，作为人才需求分析样本。",
            )],
            source_quality=SourceQuality.MEDIUM,
            claim_strength=ClaimStrength.FACT,
            bias_risk="招聘平台样本可能受城市、关键词、排序和账号状态影响，不能直接代表全市场。",
            needs_counterevidence=False,
            collected_by="boss_job_source",
            confidence=0.68,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        )
        repository.add_evidence(item)
        evidence.append(item)
        seen_keys.add(key)
        created += 1
        await emit_event(RunEvent(
            event_type="evidence_collected",
            gate="boss_job_intake",
            agent="Boss Job Source",
            message=f"已采集 Boss 职位样本：{item.source_title}",
            data={"evidence_id": item.id, "url": item.source_url, "source_channel": item.source_channel.value},
        ))

    await emit_event(RunEvent(
        event_type="node_completed",
        gate="boss_job_intake",
        agent="Boss Job Source",
        message=f"Boss 职位样本采集完成：新增 {created} 条",
        data={"created_count": created, "requested_limit": query.limit, "provider": status.provider},
    ))


async def _persist_search_evidence(
    project: ResearchProject,
    repository: SQLiteRepository,
    evidence: list[EvidenceItem],
    search_provider: SearchProvider,
    emit_event: Callable[[RunEvent], Awaitable[None]],
) -> None:
    query = (
        f"{project.domain} 招聘 JD 岗位要求 技能 薪资 经验 "
        f"{project.market_scope.value} 大模型 RAG Agent Python"
    )
    results = await search_provider.search(SearchQuery(
        query=query,
        market_scope=project.market_scope.value,
        max_results=8,
        blocked_domains=["linkedin.com", "indeed.com", "glassdoor.com"],
    ))
    seen_urls = {item.source_url for item in evidence if item.source_url}
    for result in results:
        if result.url in seen_urls:
            continue
        evidence_id = f"EV-TALENT-SEARCH-{project.id}-{len(evidence) + 1}"
        snippet = _shorten(result.snippet or result.title, 480)
        item = EvidenceItem(
            id=evidence_id,
            project_id=project.id,
            source_title=result.title,
            source_url=result.url,
            source_type=SourceType.WEB.value,
            source_channel=SourceChannel.SEARCH,
            source_policy=project.source_policy.value,
            raw_excerpt=snippet,
            snippet=snippet,
            summary=snippet,
            claims=[EvidenceClaim(
                claim_id=f"{evidence_id}-CLAIM-1",
                text=snippet,
                claim_type=ClaimType.GENERAL_FACT,
                support_level=0.45,
                requires_verification=True,
                verification_status=VerificationStatus.PARTIALLY_VERIFIED,
                evidence_ids=[evidence_id],
                notes="人才需求模式搜索补充来源，默认作为线索而非已验证事实。",
            )],
            source_quality=SourceQuality.UNKNOWN,
            claim_strength=ClaimStrength.OPINION,
            bias_risk="搜索摘要可能缺失完整 JD 上下文。",
            needs_counterevidence=True,
            collected_by="talent_demand_search",
            confidence=0.5,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        )
        repository.add_evidence(item)
        evidence.append(item)
        seen_urls.add(result.url)
        await emit_event(RunEvent(
            event_type="evidence_collected",
            gate="talent_source_intake",
            agent="Talent Source Scout",
            message=f"已记录招聘/岗位搜索来源：{result.title}",
            data={"evidence_id": item.id, "url": result.url},
        ))


def _job_dedupe_key(job: JobPostingSource) -> str:
    return "|".join([
        (job.url or "").strip().lower(),
        (job.title or "").strip().lower(),
        (job.company or "").strip().lower(),
        (job.location or "").strip().lower(),
    ])


def _job_dedupe_key_from_evidence(item: EvidenceItem) -> str:
    return "|".join([
        (item.source_url or "").strip().lower(),
        item.source_title.strip().lower(),
    ])


def _job_title(job: JobPostingSource) -> str:
    parts = [job.title]
    if job.company:
        parts.append(job.company)
    if job.location:
        parts.append(job.location)
    return " / ".join(part for part in parts if part)


def _job_to_evidence_text(job: JobPostingSource) -> str:
    lines = [
        f"岗位：{job.title}",
        f"公司：{job.company or '未知'}",
        f"地点：{job.location or '未知'}",
        f"薪资：{job.salary_text or '未提供'}",
        f"经验：{job.experience_text or '未提供'}",
        f"学历：{job.education_text or '未提供'}",
    ]
    if job.skills:
        lines.append(f"技能标签：{'、'.join(job.skills)}")
    if job.description:
        lines.append(f"职位描述：{job.description}")
    if job.url:
        lines.append(f"来源链接：{job.url}")
    return "\n".join(lines)


def _extract_postings(evidence: list[EvidenceItem], project: ResearchProject) -> list[JobPostingSignal]:
    postings: list[JobPostingSignal] = []
    for item in evidence:
        text = item.raw_excerpt or item.snippet or item.summary or ""
        extracted = extract_job_posting_signals_from_text(text, item.id)
        for posting in extracted:
            if posting.title == "未知岗位":
                posting.title = project.domain
            postings.append(posting)
    if postings:
        return postings
    return [
        JobPostingSignal(
            title=project.domain,
            skills=[],
            tools=[],
            evidence_ids=[item.id for item in evidence[:3]],
            confidence=0.2,
        )
    ]


async def _build_knowledge_base(
    *,
    project: ResearchProject,
    postings: list[JobPostingSignal],
    skill_matrix,
    evidence: list[EvidenceItem],
    llm_provider: LLMProvider | None,
) -> TalentDemandKnowledgeBase:
    fallback = _fallback_knowledge_base(project, postings, skill_matrix, evidence)
    if llm_provider is None:
        return fallback
    prompt = (
        "你是 SectorBreaker 的人才需求情报 Agent。请基于结构化岗位样本和证据，输出 TalentDemandKnowledgeBase JSON。"
        "目标是服务 HR、培训机构、课程设计和企业能力模型，不是个人求职建议。"
        "不要编造没有证据的薪资、公司或经验判断；样本不足时写入 unresolved_questions。\n\n"
        f"项目：{project.title}\n目标岗位：{project.domain}\n市场：{project.market_scope.value}\n"
        f"岗位样本：{json.dumps([item.model_dump(mode='json') for item in postings], ensure_ascii=False)}\n"
        f"技能矩阵：{json.dumps([item.model_dump(mode='json') for item in skill_matrix], ensure_ascii=False)}\n"
        f"证据摘要：{json.dumps([{'id': item.id, 'title': item.source_title, 'snippet': item.snippet[:240]} for item in evidence], ensure_ascii=False)}"
    )
    try:
        generated = await llm_provider.complete_structured(
            [ChatMessage(role="user", content=prompt)],
            TalentDemandKnowledgeBase,
        )
    except Exception:
        return fallback
    if not generated.postings:
        generated.postings = fallback.postings
    if not generated.skill_matrix:
        generated.skill_matrix = fallback.skill_matrix
    if not generated.overview:
        generated.overview = fallback.overview
    return generated


def _fallback_knowledge_base(
    project: ResearchProject,
    postings: list[JobPostingSignal],
    skill_matrix,
    evidence: list[EvidenceItem],
) -> TalentDemandKnowledgeBase:
    top_skills = [item.canonical_name for item in skill_matrix[:8]]
    overview = (
        f"`{project.domain}` 当前样本显示，需求重点集中在 "
        f"{'、'.join(top_skills) if top_skills else '岗位职责、技能栈和经验要求'}。"
        f"本轮共使用 {len(evidence)} 条证据、抽取 {len(postings)} 条岗位样本。"
    )
    role_levels = _build_role_level_notes(postings)
    salary_notes = _build_salary_experience_notes(postings)
    learning_path = _build_learning_path(top_skills)
    portfolio_requirements = _build_portfolio_requirements(top_skills, project.domain)
    unresolved = []
    if len(postings) < _MIN_TALENT_EVIDENCE:
        unresolved.append("岗位样本数量不足，需要补充更多 JD 或外部报告。")
    if not any(item.salary_text for item in postings):
        unresolved.append("薪资字段不足，不能推断薪酬区间。")
    if not any(item.experience_text for item in postings):
        unresolved.append("经验字段不足，岗位分层仍需更多证据。")
    return TalentDemandKnowledgeBase(
        overview=overview,
        postings=postings,
        skill_matrix=skill_matrix,
        role_levels=role_levels,
        company_industry_patterns=_build_company_patterns(postings),
        salary_experience_notes=salary_notes,
        learning_path=learning_path,
        portfolio_requirements=portfolio_requirements,
        unresolved_questions=unresolved,
    )


def _review_and_expand_knowledge_base(kb: TalentDemandKnowledgeBase, project: ResearchProject) -> TalentDemandKnowledgeBase:
    if not kb.learning_path and kb.skill_matrix:
        kb.learning_path = _build_learning_path([item.canonical_name for item in kb.skill_matrix[:6]])
    if not kb.portfolio_requirements and kb.skill_matrix:
        kb.portfolio_requirements = _build_portfolio_requirements(
            [item.canonical_name for item in kb.skill_matrix[:6]],
            project.domain,
        )
    if not kb.unresolved_questions and kb.source_coverage.gaps:
        kb.unresolved_questions = ["需要补充更多样本以验证当前技能频率和岗位分层。"]
    return kb


def _build_role_level_notes(postings: list[JobPostingSignal]) -> list[str]:
    counts: dict[str, int] = {}
    for posting in postings:
        counts[posting.seniority] = counts.get(posting.seniority, 0) + 1
    return [f"{level}: {count} 条样本" for level, count in sorted(counts.items())]


def _build_salary_experience_notes(postings: list[JobPostingSignal]) -> list[str]:
    notes = []
    salary_count = sum(1 for item in postings if item.salary_text)
    experience_count = sum(1 for item in postings if item.experience_text)
    if salary_count:
        notes.append(f"有 {salary_count} 条样本包含薪资字段，应按地区和公司类型继续拆分。")
    if experience_count:
        notes.append(f"有 {experience_count} 条样本包含经验字段，可用于初步岗位分层。")
    return notes


def _build_company_patterns(postings: list[JobPostingSignal]) -> list[str]:
    companies = [item.company for item in postings if item.company]
    if not companies:
        return []
    unique_companies = list(dict.fromkeys(companies))
    return [f"样本中出现 {company}，需要继续补充公司行业、规模和岗位层级背景。" for company in unique_companies[:8]]


def _build_learning_path(top_skills: list[str]) -> list[str]:
    if not top_skills:
        return []
    return [
        f"先建立 `{top_skills[0]}` 的基本概念、常见任务和实践边界。",
        f"围绕 {', '.join(top_skills[:4])} 做一个端到端小项目，验证技能是否能组合使用。",
        "补充工程化能力：API 服务、日志、评测、部署、成本和失败兜底。",
        "用真实业务场景复盘：输入是什么、输出如何评估、用户如何使用、风险如何控制。",
    ]


def _build_portfolio_requirements(top_skills: list[str], role: str) -> list[str]:
    if not top_skills:
        return []
    return [
        f"为 `{role}` 准备一个覆盖 {', '.join(top_skills[:4])} 的可运行项目。",
        "项目应包含清晰 README、架构图、数据/信源说明、评测方式和失败案例。",
        "如果面向企业端，补充权限、监控、成本估算、可维护性和安全边界。",
    ]


def _shorten(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip(" ,.;:，。") + "…"
