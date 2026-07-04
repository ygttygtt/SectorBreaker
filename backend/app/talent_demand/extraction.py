"""Conservative deterministic extraction for Chinese JD/report snippets."""

from __future__ import annotations

import re

from backend.app.talent_demand.models import JobPostingSignal, Seniority


_FIELD_PATTERNS = {
    "title": re.compile(r"^\s*(?:岗位|职位|招聘岗位|岗位名称|职位名称)\s*[:：]\s*(.+?)\s*$", re.M),
    "company": re.compile(r"^\s*(?:公司|企业|雇主|单位)\s*[:：]\s*(.+?)\s*$", re.M),
    "location": re.compile(r"^\s*(?:地点|工作地点|城市|地区)\s*[:：]\s*(.+?)\s*$", re.M),
    "salary": re.compile(r"^\s*(?:薪资|薪酬|薪资范围|薪资待遇|待遇)\s*[:：]\s*(.+?)\s*$", re.M),
    "experience": re.compile(r"^\s*(?:经验|经验要求|工作经验)\s*[:：]\s*(.+?)\s*$", re.M),
    "education": re.compile(r"^\s*(?:学历|学历要求|教育背景)\s*[:：]\s*(.+?)\s*$", re.M),
}

_TITLE_FALLBACK = re.compile(
    r"(?:招聘|诚聘|寻找)\s*([A-Za-z0-9\u4e00-\u9fff +#/.·-]{2,40}?"
    r"(?:工程师|开发|专家|架构师|顾问|经理|实习生))"
)
_SALARY_INLINE = re.compile(
    r"(?:(?:年薪|月薪|薪资|薪酬)\s*)?"
    r"\d+(?:\.\d+)?\s*(?:[-~到至]\s*\d+(?:\.\d+)?)?\s*"
    r"(?:[KkWw万千元]+)(?:/[年月])?(?:\s*[·xX]\s*\d+\s*薪)?"
)
_EXPERIENCE_INLINE = re.compile(r"(?:\d+\s*(?:[-~到至]\s*\d+)?\s*年|经验不限|应届)")
_EDUCATION_INLINE = re.compile(r"(?:博士|硕士|本科|大专|学历不限)(?:及以上)?")

_SKILL_ALIASES = {
    "LLM": ["LLM", "llm", "大模型", "大型语言模型"],
    "RAG": ["RAG", "rag", "检索增强生成"],
    "Agent": ["Agent", "agent", "智能体"],
    "Python": ["Python", "python"],
    "向量数据库": ["向量数据库", "向量库", "Vector DB", "vector database"],
}
_TOOL_ALIASES = {
    "LangChain": ["LangChain", "langchain"],
    "LangGraph": ["LangGraph", "langgraph"],
    "FastAPI": ["FastAPI", "fastapi"],
}


def extract_job_posting_signals_from_text(text: str, evidence_id: str) -> list[JobPostingSignal]:
    """Extract one conservative posting signal from JD/report text.

    The first pass intentionally avoids creative inference. It returns a single
    posting for a text block and leaves missing fields unset.
    """

    cleaned = _normalize_text(text)
    if not cleaned:
        return []

    title = _extract_labeled("title", cleaned) or _extract_title_fallback(cleaned)
    if not title:
        title = "未知岗位"

    salary_text = _extract_labeled("salary", cleaned) or _extract_inline(_SALARY_INLINE, cleaned)
    experience_text = _extract_labeled("experience", cleaned) or _extract_inline(_EXPERIENCE_INLINE, cleaned)
    education_text = _extract_labeled("education", cleaned) or _extract_inline(_EDUCATION_INLINE, cleaned)

    posting = JobPostingSignal(
        title=title,
        company=_extract_labeled("company", cleaned),
        location=_extract_labeled("location", cleaned),
        salary_text=salary_text,
        experience_text=experience_text,
        education_text=education_text,
        responsibilities=_extract_responsibilities(cleaned),
        skills=_extract_alias_hits(cleaned, _SKILL_ALIASES),
        tools=_extract_alias_hits(cleaned, _TOOL_ALIASES),
        seniority=_infer_seniority(cleaned, experience_text),
        evidence_ids=[evidence_id] if evidence_id else [],
        confidence=0.65 if title != "未知岗位" else 0.35,
    )
    return [posting]


def _normalize_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.strip().splitlines() if line.strip())


def _extract_labeled(field: str, text: str) -> str | None:
    match = _FIELD_PATTERNS[field].search(text)
    if not match:
        return None
    value = _clean_text_value(match.group(1)) if field == "title" else _clean_field_value(match.group(1))
    return value or None


def _extract_title_fallback(text: str) -> str | None:
    match = _TITLE_FALLBACK.search(text)
    if not match:
        return None
    value = _clean_text_value(match.group(1))
    return value or None


def _extract_inline(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    value = _clean_field_value(match.group(0))
    return value or None


def _clean_field_value(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().strip("。；;，,"))


def _clean_text_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("。；;，,"))


def _extract_alias_hits(text: str, aliases_by_name: dict[str, list[str]]) -> list[str]:
    hits: list[str] = []
    lower_text = text.lower()
    for canonical, aliases in aliases_by_name.items():
        if any(alias.lower() in lower_text for alias in aliases):
            hits.append(canonical)
    return hits


def _extract_responsibilities(text: str) -> list[str]:
    responsibilities: list[str] = []
    in_section = False
    for line in text.splitlines():
        if re.match(r"^(?:职责|工作职责|岗位职责)\s*[:：]?$", line):
            in_section = True
            continue
        if in_section and re.match(r"^(?:要求|任职要求|岗位要求|资格)\s*[:：]?", line):
            break
        if in_section:
            item = re.sub(r"^\d+[.、]\s*", "", line).strip()
            if item:
                responsibilities.append(item)
    return responsibilities


def _infer_seniority(text: str, experience_text: str | None) -> Seniority:
    lowered = text.lower()
    if any(token in text for token in ["负责人", "团队管理", "技术负责人", "架构负责人"]):
        return "lead"
    if any(token in text for token in ["高级", "资深"]) or "senior" in lowered:
        return "senior"
    if any(token in text for token in ["初级", "助理", "应届", "实习"]) or "junior" in lowered:
        return "junior"
    if not experience_text:
        return "unknown"

    numbers = [int(item) for item in re.findall(r"\d+", experience_text)]
    if not numbers:
        return "junior" if "应届" in experience_text else "unknown"
    minimum = min(numbers)
    if minimum <= 1:
        return "junior"
    if minimum >= 5:
        return "senior"
    return "mid"
