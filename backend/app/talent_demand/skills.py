"""Skill alias normalization and demand matrix construction."""

from __future__ import annotations

from collections import defaultdict

from backend.app.talent_demand.models import JobPostingSignal, SkillDemandItem


_ALIAS_TO_CANONICAL = {
    "llm": "LLM",
    "大模型": "LLM",
    "大型语言模型": "LLM",
    "rag": "RAG",
    "检索增强生成": "RAG",
    "知识库": "RAG",
    "agent": "Agent",
    "智能体": "Agent",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "python": "Python",
    "fastapi": "FastAPI",
    "向量数据库": "向量数据库",
    "向量库": "向量数据库",
    "vector db": "向量数据库",
    "vector database": "向量数据库",
}

_CATEGORY_BY_CANONICAL = {
    "LLM": "ai_model",
    "RAG": "ai_model",
    "Agent": "ai_model",
    "LangChain": "framework",
    "LangGraph": "framework",
    "Python": "programming",
    "FastAPI": "backend",
    "向量数据库": "data",
}


def normalize_skill_name(name: str) -> str:
    normalized = " ".join(name.strip().split())
    return _ALIAS_TO_CANONICAL.get(normalized.lower(), normalized)


def build_skill_matrix(postings: list[JobPostingSignal]) -> list[SkillDemandItem]:
    buckets: dict[str, dict[str, object]] = {}

    for posting in postings:
        names_for_posting = {
            normalize_skill_name(name)
            for name in [*posting.skills, *posting.tools]
            if name and name.strip()
        }
        for canonical_name in sorted(names_for_posting):
            bucket = buckets.setdefault(
                canonical_name,
                {
                    "aliases": set(),
                    "frequency": 0,
                    "seniority_distribution": defaultdict(int),
                    "evidence_ids": [],
                },
            )
            bucket["frequency"] = int(bucket["frequency"]) + 1
            bucket["seniority_distribution"][posting.seniority] += 1
            bucket["aliases"].update(
                name
                for name in [*posting.skills, *posting.tools]
                if normalize_skill_name(name) == canonical_name
            )
            for evidence_id in posting.evidence_ids:
                if evidence_id not in bucket["evidence_ids"]:
                    bucket["evidence_ids"].append(evidence_id)

    return [
        SkillDemandItem(
            canonical_name=name,
            aliases=sorted(bucket["aliases"]),
            category=_CATEGORY_BY_CANONICAL.get(name, "other"),
            frequency=int(bucket["frequency"]),
            seniority_distribution=dict(bucket["seniority_distribution"]),
            representative_evidence_ids=list(bucket["evidence_ids"]),
        )
        for name, bucket in sorted(
            buckets.items(), key=lambda item: (-int(item[1]["frequency"]), item[0])
        )
    ]


def taxonomy_enrichment_available() -> bool:
    """Boundary for future O*NET/ESCO enrichment; default remains offline."""

    return False
