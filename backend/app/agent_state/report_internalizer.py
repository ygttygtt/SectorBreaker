"""Internalize uploaded external AI reports into structured Agent memory."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.app.agent_state.models import (
    EntityRecord,
    KnowledgeClaim,
    KnowledgeLayerId,
    OpenQuestion,
    SectorBreakerState,
    SourceMemory,
    SourceUse,
    TrustLevel,
)


_URL_RE = re.compile(r"https?://[^\s)）\]】>\"']+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s*|\n+")
_CHINESE_TERM_RE = re.compile(r"[《「“\"]([^《》「」“”\"]{2,30})[》」”\"]")
_LATIN_TERM_RE = re.compile(r"\b[A-Z][A-Za-z0-9][A-Za-z0-9 +/_-]{1,40}\b")


class InternalizedReport(BaseModel):
    document_id: str
    source_memory: SourceMemory
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    entities: list[EntityRecord] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    citation_urls: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ReportInternalizerConfig:
    max_claims: int = 12
    max_entities: int = 16
    max_questions: int = 8
    max_summary_chars: int = 900


class ReportInternalizer:
    """Turn DeepSearch-style reports into low-trust structured memory."""

    def __init__(self, config: ReportInternalizerConfig | None = None) -> None:
        self.config = config or ReportInternalizerConfig()

    def internalize(self, document: Any, *, domain: str) -> InternalizedReport:
        content = getattr(document, "content", "") or ""
        document_id = getattr(document, "id", f"doc-{uuid4().hex[:8]}")
        title = getattr(document, "file_name", None) or f"外部报告 {document_id}"
        urls = self._extract_urls(content)
        summary = self._summarize(content)
        source_memory = SourceMemory(
            source_id=document_id,
            source_kind=getattr(document, "channel", "assistant_brief"),
            title=title,
            summary=summary,
            use=SourceUse.CONTEXT,
            trust_level=TrustLevel.LOW if getattr(document, "channel", "") == "assistant_brief" else TrustLevel.MEDIUM,
            keep_reason="上传报告是用户提供的重要研究输入，应进入 Master Agent 初始上下文，但默认不视为已验证事实。",
        )
        entities = self._extract_entities(content, domain)
        claims = self._extract_claims(content, source_memory.id, document_id)
        questions = self._extract_open_questions(content)
        return InternalizedReport(
            document_id=document_id,
            source_memory=source_memory.model_copy(update={
                "extracted_entity_ids": [item.id for item in entities],
                "extracted_claim_ids": [item.id for item in claims],
            }),
            claims=claims,
            entities=entities,
            open_questions=questions,
            citation_urls=urls,
        )

    def apply_to_state(self, state: SectorBreakerState, report: InternalizedReport) -> None:
        state.shared_knowledge.source_memories.append(report.source_memory)
        state.shared_knowledge.entities.extend(report.entities)
        state.shared_knowledge.claims.extend(report.claims)
        state.shared_knowledge.open_questions.extend(report.open_questions)
        for claim in report.claims:
            state.evidence_refs.extend(claim.evidence_ids)
        state.evidence_refs = list(dict.fromkeys(state.evidence_refs))

    def _extract_claims(self, text: str, source_memory_id: str, document_id: str) -> list[KnowledgeClaim]:
        claims: list[KnowledgeClaim] = []
        for index, sentence in enumerate(self._sentences(text), start=1):
            if len(sentence) < 18:
                continue
            if self._looks_like_question(sentence):
                continue
            layer_ids = self._infer_layers(sentence)
            claims.append(KnowledgeClaim(
                id=f"CLM-REPORT-{document_id}-{index}",
                text=sentence[:420],
                layer_ids=layer_ids,
                evidence_ids=[f"DOC-{document_id}"],
                source_memory_ids=[source_memory_id],
                confidence=0.42,
                trust_level=TrustLevel.LOW,
                verification_status="unverified",
                needs_verification=True,
                notes="来自外部 AI/用户报告，已内化为低可信研究主张，后续应复核。",
            ))
            if len(claims) >= self.config.max_claims:
                break
        return claims

    def _extract_entities(self, text: str, domain: str) -> list[EntityRecord]:
        terms: list[str] = []
        terms.append(domain)
        terms.extend(match.group(1).strip() for match in _CHINESE_TERM_RE.finditer(text))
        terms.extend(match.group(0).strip() for match in _LATIN_TERM_RE.finditer(text))
        normalized = []
        seen = set()
        for term in terms:
            cleaned = term.strip(" -—:：,，.。")
            if len(cleaned) < 2 or cleaned.lower() in seen:
                continue
            seen.add(cleaned.lower())
            normalized.append(cleaned)
            if len(normalized) >= self.config.max_entities:
                break
        return [
            EntityRecord(
                name=term,
                entity_type=self._infer_entity_type(term),
                layer_ids=self._infer_layers(term),
                summary=f"从上传报告中识别出的领域相关实体或术语：{term}",
                confidence=0.45,
            )
            for term in normalized
        ]

    def _extract_open_questions(self, text: str) -> list[OpenQuestion]:
        questions: list[OpenQuestion] = []
        for sentence in self._sentences(text):
            if self._looks_like_question(sentence) or any(marker in sentence for marker in ("待验证", "尚不清楚", "需要进一步", "未知")):
                questions.append(OpenQuestion(
                    question=sentence[:240],
                    layer_ids=self._infer_layers(sentence),
                    reason="外部报告中出现的问题、限制或待验证表达。",
                    suggested_actions=["补充搜索", "查找原始来源", "交叉验证"],
                ))
            if len(questions) >= self.config.max_questions:
                break
        return questions

    def _summarize(self, text: str) -> str:
        sentences = self._sentences(text)
        summary = " ".join(sentences[:4]) if sentences else text
        if len(summary) > self.config.max_summary_chars:
            return summary[: self.config.max_summary_chars - 1].rstrip(" ,.;:，。") + "…"
        return summary

    @staticmethod
    def _extract_urls(text: str) -> list[str]:
        return list(dict.fromkeys(match.group(0).rstrip(".,;，。") for match in _URL_RE.finditer(text)))

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [
            item.strip()
            for item in _SENTENCE_SPLIT_RE.split(text.replace("\r", "\n"))
            if item and item.strip()
        ]

    @staticmethod
    def _looks_like_question(text: str) -> bool:
        return text.endswith(("?", "？")) or any(marker in text for marker in ("为什么", "如何", "怎么", "是否", "能不能"))

    @staticmethod
    def _infer_entity_type(term: str) -> str:
        lowered = term.lower()
        if any(marker in lowered for marker in ("api", "sdk", "framework", "langgraph", "rag")):
            return "tool_or_technology"
        if any(marker in term for marker in ("公司", "机构", "平台", "玩家")):
            return "player"
        if any(marker in term for marker in ("政策", "监管", "风险", "合规")):
            return "risk_or_policy"
        return "concept"

    @staticmethod
    def _infer_layers(text: str) -> list[KnowledgeLayerId]:
        lowered = text.lower()
        layers: list[KnowledgeLayerId] = []
        if any(marker in text for marker in ("是什么", "为什么", "需求", "痛点", "概念", "定义")):
            layers.append(KnowledgeLayerId.WHAT_WHY)
        if any(marker in text for marker in ("谁", "用户", "玩家", "机构", "公司", "博主", "社区")):
            layers.append(KnowledgeLayerId.WHO)
        if any(marker in lowered for marker in ("how", "api", "sdk", "框架", "工具", "流程", "实现", "搭建", "技术", "协议")):
            layers.append(KnowledgeLayerId.HOW)
        if any(marker in text for marker in ("赚钱", "成本", "价格", "营收", "商业", "供应链", "外包")):
            layers.append(KnowledgeLayerId.MONEY)
        if any(marker in text for marker in ("风险", "政策", "监管", "合规", "骗局", "灰产", "封号", "不稳定")):
            layers.append(KnowledgeLayerId.RISKS)
        return layers or [KnowledgeLayerId.WHAT_WHY]
