"""Render talent-demand knowledge bases into Obsidian-ready artifacts."""

from __future__ import annotations

import json
import re
from collections import defaultdict

from backend.app.schemas import Artifact, ArtifactType, ResearchProject
from backend.app.talent_demand.models import (
    JobPostingSignal,
    SkillDemandItem,
    SourceCoverageMatrix,
    TalentDemandKnowledgeBase,
)


def build_talent_demand_artifacts(
    *,
    project: ResearchProject,
    knowledge_base: TalentDemandKnowledgeBase,
) -> list[Artifact]:
    evidence_ids = _knowledge_base_evidence_ids(knowledge_base)
    artifacts = [
        _artifact(
            project,
            "ART-TALENT-OVERVIEW",
            ArtifactType.TALENT_DEMAND_OVERVIEW,
            "岗位需求总览",
            "00-岗位需求总览.md",
            _render_overview(project, knowledge_base),
            evidence_ids,
        ),
        _artifact(
            project,
            "ART-TALENT-ROLE-PROFILE",
            ArtifactType.TALENT_ROLE_PROFILE,
            "岗位画像与分层",
            "01-岗位画像与分层.md",
            _render_role_profile(knowledge_base.postings, knowledge_base.role_levels),
            evidence_ids,
        ),
        _artifact(
            project,
            "ART-TALENT-SKILL-MATRIX",
            ArtifactType.TALENT_SKILL_MATRIX,
            "技能需求矩阵",
            "02-技能需求矩阵.md",
            _render_skill_matrix(knowledge_base.skill_matrix),
            evidence_ids,
        ),
        _artifact(
            project,
            "ART-TALENT-COMPANY-DISTRIBUTION",
            ArtifactType.TALENT_COMPANY_DISTRIBUTION,
            "公司与行业分布",
            "03-公司与行业分布.md",
            _render_company_distribution(knowledge_base),
            evidence_ids,
        ),
        _artifact(
            project,
            "ART-TALENT-SALARY-EXPERIENCE",
            ArtifactType.TALENT_SALARY_EXPERIENCE,
            "薪资与经验要求",
            "04-薪资与经验要求.md",
            _render_salary_experience(knowledge_base),
            evidence_ids,
        ),
        _artifact(
            project,
            "ART-TALENT-CAPABILITY-MODEL",
            ArtifactType.TALENT_CAPABILITY_MODEL,
            "学习路径与能力模型",
            "05-学习路径与能力模型.md",
            _render_capability_model(knowledge_base),
            evidence_ids,
        ),
        _artifact(
            project,
            "ART-TALENT-PORTFOLIO",
            ArtifactType.TALENT_PORTFOLIO_REQUIREMENTS,
            "作品集与项目要求",
            "06-作品集与项目要求.md",
            _render_portfolio_requirements(knowledge_base),
            evidence_ids,
        ),
        _artifact(
            project,
            "ART-TALENT-UNRESOLVED",
            ArtifactType.TALENT_UNRESOLVED_QUESTIONS,
            "待验证问题",
            "99-待验证问题.md",
            _render_unresolved_questions(knowledge_base),
            evidence_ids,
        ),
    ]
    artifacts.extend(_render_skill_cards(project, knowledge_base.skill_matrix))
    artifacts.extend(_render_role_cards(project, knowledge_base.postings))
    artifacts.extend(_render_company_cards(project, knowledge_base.postings))
    return artifacts


def _artifact(
    project: ResearchProject,
    artifact_id: str,
    artifact_type: ArtifactType,
    title: str,
    content_path: str,
    content: str,
    evidence_ids: list[str],
    schema_version: str = "talent-v1",
) -> Artifact:
    return Artifact(
        id=f"{artifact_id}-{project.id}",
        project_id=project.id,
        artifact_type=artifact_type,
        title=title,
        content_path=content_path,
        content=content,
        source_evidence_ids=evidence_ids,
        schema_version=schema_version,
    )


def _render_overview(project: ResearchProject, kb: TalentDemandKnowledgeBase) -> str:
    coverage = kb.source_coverage
    lines = [
        f"# {project.domain} 人才需求总览",
        "",
        kb.overview or f"本库围绕 `{project.domain}` 的岗位需求、技能信号、经验薪资线索和学习路径建立。",
        "",
        "## Source Coverage Matrix",
        "",
        _coverage_table(coverage),
        "",
        "```json source_coverage",
        json.dumps(coverage.model_dump(mode="json"), ensure_ascii=False, indent=2),
        "```",
        "",
        "## 如何解读",
        "",
        "- 这不是个人求职建议，而是用于招聘画像、课程设计、企业培训或能力模型建设的需求情报库。",
        "- 样本越多，技能频率和薪资经验判断越可靠；样本不足时请优先查看 `99-待验证问题`。",
        "- 搜索结果默认只是线索，上传 JD、外部调研报告和官方/企业来源能显著提高可信度。",
    ]
    if coverage.gaps:
        lines.extend(["", "## 当前限制", "", *_bullet_lines(_gap_to_sentence(gap) for gap in coverage.gaps)])
    return "\n".join(lines)


def _render_role_profile(postings: list[JobPostingSignal], role_levels: list[str]) -> str:
    grouped: dict[str, list[JobPostingSignal]] = defaultdict(list)
    for posting in postings:
        grouped[posting.seniority].append(posting)

    lines = ["# 岗位画像与分层", ""]
    if role_levels:
        lines.extend(["## 分层摘要", "", *_bullet_lines(role_levels), ""])
    for seniority in ["junior", "mid", "senior", "lead", "unknown"]:
        items = grouped.get(seniority, [])
        if not items:
            continue
        lines.extend([f"## {seniority}", ""])
        for item in items:
            evidence = _evidence_suffix(item.evidence_ids)
            lines.append(f"- **{item.title}**{_optional_company_location(item)}{evidence}")
            if item.responsibilities:
                lines.append(f"  - 职责信号：{'；'.join(item.responsibilities[:3])}")
            if item.skills or item.tools:
                lines.append(f"  - 技能/工具：{', '.join([*item.skills, *item.tools])}")
        lines.append("")
    if len(lines) <= 2:
        lines.append("当前样本不足，暂未形成可解释的岗位分层。")
    return "\n".join(lines)


def _render_skill_matrix(skill_matrix: list[SkillDemandItem]) -> str:
    lines = [
        "# 技能需求矩阵",
        "",
        "| 技能 | 类别 | 频次 | 分层分布 | 别名 | 代表证据 |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    if not skill_matrix:
        lines.append("| 样本不足 | other | 0 | - | - | - |")
    for item in skill_matrix:
        aliases = ", ".join(item.aliases) or "-"
        distribution = ", ".join(f"{key}:{value}" for key, value in item.seniority_distribution.items()) or "-"
        evidence = ", ".join(item.representative_evidence_ids) or "-"
        lines.append(
            f"| [[{item.canonical_name}]] | {item.category} | {item.frequency} | "
            f"{distribution} | {aliases} | {evidence} |"
        )
    lines.extend([
        "",
        "## 使用建议",
        "",
        "- 高频技能适合作为招聘筛选、课程模块或企业培训主线。",
        "- 低频但高价值技能不要直接删除，应结合岗位层级和公司类型继续验证。",
        "- 同义词已做第一版归一化，后续可接 ESCO/O*NET/Lightcast 等 taxonomy adapter。",
    ])
    return "\n".join(lines)


def _render_company_distribution(kb: TalentDemandKnowledgeBase) -> str:
    lines = ["# 公司与行业分布", ""]
    if kb.company_industry_patterns:
        lines.extend(_bullet_lines(kb.company_industry_patterns))
    else:
        companies = [posting.company for posting in kb.postings if posting.company]
        if companies:
            lines.extend(_bullet_lines(f"{company} 出现在样本中，需继续补充行业、规模和岗位层级信息。" for company in companies))
        else:
            lines.append("当前证据没有稳定公司/行业字段。建议补充企业招聘页、JD 汇总或外部调研报告。")
    return "\n".join(lines)


def _render_salary_experience(kb: TalentDemandKnowledgeBase) -> str:
    lines = ["# 薪资与经验要求", ""]
    salary_items = [posting for posting in kb.postings if posting.salary_text]
    experience_items = [posting for posting in kb.postings if posting.experience_text]
    if salary_items:
        lines.extend(["## 薪资信号", ""])
        lines.extend(_bullet_lines(f"{item.title}: {item.salary_text}{_evidence_suffix(item.evidence_ids)}" for item in salary_items))
    else:
        lines.extend(["## 薪资信号", "", "当前样本未提供足够薪资字段，不应推断薪资区间。"])
    lines.extend(["", "## 经验信号", ""])
    if experience_items:
        lines.extend(_bullet_lines(f"{item.title}: {item.experience_text}{_evidence_suffix(item.evidence_ids)}" for item in experience_items))
    else:
        lines.append("当前样本未提供足够经验字段，需要补充 JD 样本。")
    if kb.salary_experience_notes:
        lines.extend(["", "## 综合判断", "", *_bullet_lines(kb.salary_experience_notes)])
    return "\n".join(lines)


def _render_capability_model(kb: TalentDemandKnowledgeBase) -> str:
    lines = ["# 学习路径与能力模型", ""]
    if kb.learning_path:
        lines.extend(["## 建议学习路径", "", *_numbered_lines(kb.learning_path), ""])
    else:
        top_skills = [item.canonical_name for item in kb.skill_matrix[:6]]
        if top_skills:
            lines.extend(["## 建议学习路径", "", *_numbered_lines([f"围绕 {skill} 建立可验证能力。" for skill in top_skills]), ""])
        else:
            lines.append("当前技能样本不足，建议先补充 JD 或外部报告。")
    lines.extend(["## 能力模型视角", ""])
    lines.extend(_bullet_lines([
        "基础能力：编程、工程化、调试和文档理解。",
        "核心能力：把业务问题转成可运行的模型/API/RAG/Agent 系统。",
        "验证能力：能用指标、日志、评测集和用户反馈证明方案有效。",
    ]))
    return "\n".join(lines)


def _render_portfolio_requirements(kb: TalentDemandKnowledgeBase) -> str:
    lines = ["# 作品集与项目要求", ""]
    if kb.portfolio_requirements:
        lines.extend(_bullet_lines(kb.portfolio_requirements))
    else:
        top_skills = [item.canonical_name for item in kb.skill_matrix[:5]]
        if top_skills:
            lines.extend(_bullet_lines([
                f"围绕 {', '.join(top_skills)} 做一个可演示、可部署、可解释的项目。",
                "项目 README 应说明目标用户、数据来源、架构、评测方式和失败边界。",
                "如果岗位强调生产工程，需要补充 API 服务、监控、权限、成本和容错设计。",
            ]))
        else:
            lines.append("当前证据不足，暂不生成具体作品集建议。")
    return "\n".join(lines)


def _render_unresolved_questions(kb: TalentDemandKnowledgeBase) -> str:
    questions = list(kb.unresolved_questions)
    questions.extend(_gap_to_sentence(gap) for gap in kb.source_coverage.gaps)
    unique_questions = list(dict.fromkeys(item for item in questions if item))
    lines = ["# 待验证问题", ""]
    if unique_questions:
        lines.extend(_numbered_lines(unique_questions))
    else:
        lines.append("当前没有阻塞性待验证问题，但仍建议继续补充更多 JD 样本和高质量信源。")
    return "\n".join(lines)


def _render_skill_cards(project: ResearchProject, skill_matrix: list[SkillDemandItem]) -> list[Artifact]:
    artifacts: list[Artifact] = []
    for item in skill_matrix:
        content = "\n".join([
            f"# {item.canonical_name}",
            "",
            f"**类别**：{item.category}",
            f"**出现频次**：{item.frequency}",
            f"**别名**：{', '.join(item.aliases) or '-'}",
            f"**代表证据**：{', '.join(item.representative_evidence_ids) or '-'}",
            "",
            "## 为什么重要",
            "",
            f"`{item.canonical_name}` 在当前样本中被反复提及，说明它可能是岗位筛选、课程设计或能力模型中的关键节点。",
        ])
        artifacts.append(_artifact(
            project,
            f"ART-TALENT-SKILL-{_slugify(item.canonical_name)}",
            ArtifactType.TALENT_SKILL_MATRIX,
            item.canonical_name,
            f"skills/{_safe_filename(item.canonical_name)}.md",
            content,
            item.representative_evidence_ids,
            schema_version="talent-v1-card",
        ))
    return artifacts


def _render_role_cards(project: ResearchProject, postings: list[JobPostingSignal]) -> list[Artifact]:
    artifacts: list[Artifact] = []
    grouped: dict[str, list[JobPostingSignal]] = defaultdict(list)
    for posting in postings:
        grouped[posting.seniority].append(posting)
    for seniority, items in grouped.items():
        evidence_ids = _unique_evidence_ids(items)
        content = "\n".join([
            f"# {seniority} 岗位层级",
            "",
            f"样本数量：{len(items)}",
            "",
            "## 典型要求",
            "",
            *_bullet_lines(_posting_summary(item) for item in items[:8]),
        ])
        artifacts.append(_artifact(
            project,
            f"ART-TALENT-ROLE-{seniority.upper()}",
            ArtifactType.TALENT_ROLE_PROFILE,
            f"{seniority} 岗位层级",
            f"roles/{_safe_filename(seniority)}.md",
            content,
            evidence_ids,
            schema_version="talent-v1-card",
        ))
    return artifacts


def _render_company_cards(project: ResearchProject, postings: list[JobPostingSignal]) -> list[Artifact]:
    artifacts: list[Artifact] = []
    grouped: dict[str, list[JobPostingSignal]] = defaultdict(list)
    for posting in postings:
        if posting.company:
            grouped[posting.company].append(posting)
    for company, items in grouped.items():
        evidence_ids = _unique_evidence_ids(items)
        content = "\n".join([
            f"# {company}",
            "",
            "## 样本岗位",
            "",
            *_bullet_lines(_posting_summary(item) for item in items[:8]),
            "",
            "## 使用提醒",
            "",
            "单一公司样本不能代表整个市场，只能作为岗位需求线索。",
        ])
        artifacts.append(_artifact(
            project,
            f"ART-TALENT-COMPANY-{_slugify(company)}",
            ArtifactType.TALENT_COMPANY_DISTRIBUTION,
            company,
            f"companies/{_safe_filename(company)}.md",
            content,
            evidence_ids,
            schema_version="talent-v1-card",
        ))
    return artifacts


def _coverage_table(coverage: SourceCoverageMatrix) -> str:
    rows = [
        ("总证据", coverage.total_evidence),
        ("上传 JD/用户材料", coverage.uploaded_jd_count),
        ("上传外部报告", coverage.uploaded_report_count),
        ("搜索结果", coverage.search_result_count),
        ("抽取/可靠 provider", coverage.extracted_page_count),
        ("标准/系统来源", coverage.occupation_standard_count),
        ("薪资信号", coverage.salary_signal_count),
        ("经验信号", coverage.experience_signal_count),
        ("技能信号", coverage.skill_signal_count),
        ("弱/未验证证据", coverage.weak_or_unverified_count),
    ]
    lines = ["| 指标 | 数量 |", "| --- | ---: |"]
    lines.extend(f"| {label} | {value} |" for label, value in rows)
    return "\n".join(lines)


def _knowledge_base_evidence_ids(kb: TalentDemandKnowledgeBase) -> list[str]:
    ids: list[str] = []
    ids.extend(_unique_evidence_ids(kb.postings))
    for item in kb.skill_matrix:
        ids.extend(item.representative_evidence_ids)
    return list(dict.fromkeys(ids))


def _unique_evidence_ids(postings: list[JobPostingSignal]) -> list[str]:
    ids: list[str] = []
    for posting in postings:
        ids.extend(posting.evidence_ids)
    return list(dict.fromkeys(ids))


def _posting_summary(posting: JobPostingSignal) -> str:
    details = []
    if posting.company:
        details.append(posting.company)
    if posting.location:
        details.append(posting.location)
    if posting.experience_text:
        details.append(f"经验 {posting.experience_text}")
    if posting.salary_text:
        details.append(f"薪资 {posting.salary_text}")
    if posting.skills or posting.tools:
        details.append(f"技能 {', '.join([*posting.skills, *posting.tools])}")
    suffix = f"（{'，'.join(details)}）" if details else ""
    return f"{posting.title}{suffix}{_evidence_suffix(posting.evidence_ids)}"


def _optional_company_location(posting: JobPostingSignal) -> str:
    parts = [part for part in [posting.company, posting.location] if part]
    return f"（{' / '.join(parts)}）" if parts else ""


def _evidence_suffix(evidence_ids: list[str]) -> str:
    return f" [{', '.join(evidence_ids)}]" if evidence_ids else ""


def _gap_to_sentence(gap: str) -> str:
    mapping = {
        "low_sample": "样本数量偏低：需要补充更多 JD、企业招聘页或外部报告。",
        "no_salary_signal": "薪资信号缺失：不能直接推断薪酬区间。",
        "no_experience_signal": "经验要求缺失：岗位分层判断需要更多样本。",
        "search_only_evidence": "当前主要依赖搜索摘要：建议上传 JD/报告或抽取原网页正文。",
    }
    return mapping.get(gap, gap)


def _bullet_lines(items) -> list[str]:
    return [f"- {item}" for item in items if item]


def _numbered_lines(items) -> list[str]:
    return [f"{index}. {item}" for index, item in enumerate([item for item in items if item], start=1)]


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\n\r\t]+', "-", value).strip(" .-")
    return cleaned or "untitled"


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9一-鿿]+", "-", value).strip("-").upper() or "UNTITLED"
