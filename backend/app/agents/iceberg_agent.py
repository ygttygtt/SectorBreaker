"""Optional iceberg/risk-surface investigation helpers.

The goal is to understand hidden risks, scams, grey-market incentives, and
fragility points. It must not produce operational wrongdoing instructions.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from backend.app.agent_state.models import (
    KnowledgeClaim,
    KnowledgeLayerId,
    OpenQuestion,
    SourceMemory,
    SourceUse,
    TrustLevel,
)


_OPERATIONAL_RISK_MARKERS = (
    "教程",
    "步骤",
    "脚本",
    "注册机",
    "绕过",
    "规避",
    "批量注册",
    "接码",
    "盗号",
    "破解",
    "攻击",
)


class IcebergSeedPlan(BaseModel):
    domain: str
    seed_queries: list[str]
    reason: str


class IcebergRiskFinding(BaseModel):
    term: str
    category: str = "risk_signal"
    summary: str
    related_queries: list[str] = Field(default_factory=list)
    allowed_for_output: bool = True
    safety_note: str = ""


class IcebergRiskAgent:
    """Build safe seed plans and filter risky operational detail."""

    def build_seed_plan(self, domain: str) -> IcebergSeedPlan:
        domain_text = domain.strip()
        return IcebergSeedPlan(
            domain=domain_text,
            seed_queries=[
                f"{domain_text} 风险 骗局 防坑",
                f"{domain_text} 灰产 内幕 产业链",
                f"{domain_text} 投诉 监管 合规",
                f"{domain_text} 常见套路 脆弱点",
            ],
            reason="用风险/防坑/监管/产业链视角自举领域黑话和水面下问题，而不是直接生成操作教程。",
        )

    def extract_risk_terms(self, text: str, *, domain: str) -> list[IcebergRiskFinding]:
        candidates = self._candidate_terms(text)
        findings: list[IcebergRiskFinding] = []
        seen: set[str] = set()
        for term in candidates:
            if term.lower() in seen or len(term) < 2:
                continue
            seen.add(term.lower())
            allowed, note = self._safety(term)
            findings.append(IcebergRiskFinding(
                term=term,
                category=self._category(term),
                summary=f"{term} 可能是 {domain} 领域的风险信号、黑话、争议服务或隐藏链路，需要作为 L5 风险/边界材料理解。",
                related_queries=[
                    f"{domain} {term} 风险 防坑",
                    f"{domain} {term} 监管 合规",
                ],
                allowed_for_output=allowed,
                safety_note=note,
            ))
            if len(findings) >= 12:
                break
        return findings

    def redact_operational_detail(self, text: str) -> str:
        sanitized = text
        for marker in _OPERATIONAL_RISK_MARKERS:
            sanitized = re.sub(
                rf"[^。！？.!?\n]{{0,30}}{re.escape(marker)}[^。！？.!?\n]{{0,80}}",
                f"【已移除可能导致滥用的“{marker}”操作细节】",
                sanitized,
                flags=re.IGNORECASE,
            )
        return sanitized

    def findings_to_state_objects(
        self,
        *,
        domain: str,
        findings: list[IcebergRiskFinding],
        source_id: str = "iceberg-risk-agent",
    ) -> tuple[list[SourceMemory], list[KnowledgeClaim], list[OpenQuestion]]:
        source_memories: list[SourceMemory] = []
        claims: list[KnowledgeClaim] = []
        questions: list[OpenQuestion] = []
        for index, finding in enumerate(findings, start=1):
            memory_id = f"SM-ICE-{index}"
            source_memories.append(SourceMemory(
                id=memory_id,
                source_id=source_id,
                source_kind="iceberg_risk_scan",
                title=f"{domain} 风险信号：{finding.term}",
                summary=finding.summary,
                use=SourceUse.VERIFY,
                trust_level=TrustLevel.LOW,
                related_layer_ids=[KnowledgeLayerId.RISKS, KnowledgeLayerId.MONEY],
                keep_reason="冰山探测输出的风险/激励线索，应进入 L5 风险和 L4 激励待验证材料。",
            ))
            claims.append(KnowledgeClaim(
                id=f"CLM-ICE-{index}",
                text=f"{finding.term} 可能是 {domain} 领域的风险、骗局、灰色激励或隐藏链路信号，需要作为风险面理解。",
                layer_ids=[KnowledgeLayerId.RISKS, KnowledgeLayerId.MONEY],
                source_memory_ids=[memory_id],
                confidence=0.35,
                trust_level=TrustLevel.LOW,
                verification_status="unverified",
                needs_verification=True,
                notes=finding.safety_note or "冰山探测线索，需继续验证。",
            ))
            questions.append(OpenQuestion(
                id=f"OQ-ICE-{index}",
                question=f"{domain} 中的“{finding.term}”到底是误导信息、骗局风险、真实产业链环节，还是普通术语？",
                layer_ids=[KnowledgeLayerId.RISKS, KnowledgeLayerId.MONEY],
                reason="冰山探测发现的待验证风险信号。",
                suggested_actions=finding.related_queries,
            ))
        return source_memories, claims, questions

    @staticmethod
    def _candidate_terms(text: str) -> list[str]:
        quoted = re.findall(r"[《「“\"]([^《》「」“”\"]{2,24})[》」”\"]", text)
        marker_terms = re.findall(
            r"([\u4e00-\u9fffA-Za-z0-9]{2,18}(?:骗局|套路|灰产|黑产|代办|包过|保录取|造假|外挂|封号|套利|中介|号池))",
            text,
            flags=re.IGNORECASE,
        )
        operational_terms = re.findall(
            r"([\u4e00-\u9fffA-Za-z0-9]{0,10}(?:接码|注册机|批量注册|指纹浏览器|代理IP)[\u4e00-\u9fffA-Za-z0-9]{0,10})",
            text,
            flags=re.IGNORECASE,
        )
        latin_terms = re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,24}\b", text)
        return list(dict.fromkeys(quoted + marker_terms + operational_terms + latin_terms))

    @staticmethod
    def _category(term: str) -> str:
        if any(marker in term for marker in ("政策", "监管", "合规", "封号")):
            return "policy_or_platform_risk"
        if any(marker in term for marker in ("骗局", "套路", "造假", "包过", "保录取")):
            return "scam_or_fraud_signal"
        if any(marker in term for marker in ("灰产", "黑产", "套利", "号池")):
            return "grey_market_signal"
        return "risk_signal"

    @staticmethod
    def _safety(term: str) -> tuple[bool, str]:
        if any(marker in term for marker in _OPERATIONAL_RISK_MARKERS):
            return False, "该术语可能涉及可执行滥用链路，只能做高层风险解释，不能输出操作步骤。"
        return True, "可作为风险/防坑/产业链理解材料。"
