"""Structured state and memory models for SectorBreaker V2.

These models intentionally sit outside the older ``ResearchState``. The older
state tracks workflow progress; this module tracks the Agent's cognition:
what it knows, what it is trying to learn, what it should keep, and what should
stay as short-lived working memory.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class KnowledgeLayerId(StrEnum):
    PREREQUISITE = "L0_prerequisite_basics"
    WHAT_WHY = "L1_what_why"
    WHO = "L2_who"
    HOW = "L3_how"
    MONEY = "L4_money_incentives"
    RISKS = "L5_risks_boundaries"


class CoverageStatus(StrEnum):
    NOT_STARTED = "not_started"
    NEEDS_MORE = "needs_more"
    DEGRADED = "degraded"
    SUFFICIENT = "sufficient"
    BLOCKED = "blocked"


class SourceUse(StrEnum):
    CONTEXT = "context"
    EVIDENCE = "evidence"
    SEARCH_LEAD = "search_lead"
    VERIFY = "verify"
    REJECTED = "rejected"


class TrustLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class AgentAction(StrEnum):
    CONTINUE = "continue"
    SEARCH_AGAIN = "search_again"
    DISPATCH_TASK = "dispatch_task"
    ASK_USER = "ask_user"
    DEGRADE = "degrade"
    BLOCK = "block"
    EXPORT = "export"


class RelationshipType(StrEnum):
    PREREQUISITE_OF = "prerequisite_of"
    PART_OF = "part_of"
    IMPLEMENTS = "implements"
    ENABLES = "enables"
    COMPETES_WITH = "competes_with"
    DEPENDS_ON = "depends_on"
    RISKS = "risks"
    MITIGATES = "mitigates"
    RELATED_TO = "related_to"


class MetaContext(BaseModel):
    project_id: str
    domain: str
    market_scope: str = "mixed"
    source_policy: str = "reliable_first"
    product_mode: str = "domain_knowledge"
    user_goal: str
    user_level: str = "unknown"
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    safety_policies: list[str] = Field(default_factory=list)


class KnowledgeLayer(BaseModel):
    id: KnowledgeLayerId
    title: str
    goal: str
    guiding_questions: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    required_evidence_types: list[str] = Field(default_factory=list)
    card_titles: list[str] = Field(default_factory=list)
    open_question_ids: list[str] = Field(default_factory=list)
    coverage_status: CoverageStatus = CoverageStatus.NOT_STARTED
    coverage_notes: str = ""

    @field_validator("guiding_questions", "completion_criteria", "required_evidence_types")
    @classmethod
    def strip_list_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


class KnowledgeSchema(BaseModel):
    schema_id: str = Field(default_factory=lambda: f"KS-{uuid4().hex[:12]}")
    domain: str
    strategy: str = "dynamic_practical_cognition"
    layers: list[KnowledgeLayer]
    generated_reason: str = ""

    @classmethod
    def default_for_domain(cls, domain: str, *, include_prerequisite: bool = False) -> "KnowledgeSchema":
        layers: list[KnowledgeLayer] = []
        if include_prerequisite:
            layers.append(KnowledgeLayer(
                id=KnowledgeLayerId.PREREQUISITE,
                title="L0 前置扫盲",
                goal="补齐用户理解该领域所需的基础常识。",
                guiding_questions=["理解这个领域前，用户必须先知道哪些基础概念？"],
                completion_criteria=["能解释后续核心文档里依赖的前置概念。"],
                required_evidence_types=["beginner_explainer", "trusted_reference"],
            ))
        layers.extend([
            KnowledgeLayer(
                id=KnowledgeLayerId.WHAT_WHY,
                title="L1 本源与需求",
                goal=f"解释 {domain} 是什么、为什么存在、解决什么问题。",
                guiding_questions=["它是什么？", "为什么会产生这个需求？", "它解决谁的什么痛点？"],
                completion_criteria=["能用小白能懂的语言说明领域边界和存在理由。"],
                required_evidence_types=["overview", "official_or_report", "example"],
            ),
            KnowledgeLayer(
                id=KnowledgeLayerId.WHO,
                title="L2 角色与玩家",
                goal="识别用户、提供方、头部玩家、关键资源持有者和社区。",
                guiding_questions=["谁在用？", "谁在提供？", "主流玩家是谁？", "关键资源掌握在谁手里？"],
                completion_criteria=["能列出主要角色并说明它们之间的关系。"],
                required_evidence_types=["player", "case", "community_or_company"],
            ),
            KnowledgeLayer(
                id=KnowledgeLayerId.HOW,
                title="L3 原理与实操",
                goal="拆解实现原理、工具、流程、准备工作和隐藏术语。",
                guiding_questions=["它怎么实现？", "需要什么工具/框架/资源？", "发现黑话时是否需要继续下钻？"],
                completion_criteria=["能说明关键流程，并把未知术语转成可继续追问的任务。"],
                required_evidence_types=["technical_doc", "tutorial", "implementation_case"],
            ),
            KnowledgeLayer(
                id=KnowledgeLayerId.MONEY,
                title="L4 商业与激励",
                goal="说明价值流、成本、盈利方式、上下游、外包环节和激励结构。",
                guiding_questions=["谁付钱？", "怎么赚钱？", "成本在哪里？", "哪些环节可以外包？"],
                completion_criteria=["能画出基本价值链和商业闭环。"],
                required_evidence_types=["pricing", "business_case", "supply_chain"],
            ),
            KnowledgeLayer(
                id=KnowledgeLayerId.RISKS,
                title="L5 风险与边界",
                goal="识别政策、平台、技术、伦理、安全和稳定性边界。",
                guiding_questions=["有什么风险？", "哪些地方不稳定？", "有哪些骗局、灰色链路或监管限制？"],
                completion_criteria=["能解释风险面和边界，但不提供违法或滥用操作指南。"],
                required_evidence_types=["policy", "risk_case", "warning"],
            ),
        ])
        return cls(
            domain=domain,
            layers=layers,
            generated_reason="默认使用 L0-L5 实战认知模型，后续可由 Master Agent 根据用户反馈扩展。",
        )

    def layer(self, layer_id: KnowledgeLayerId | str) -> KnowledgeLayer | None:
        normalized = KnowledgeLayerId(layer_id) if not isinstance(layer_id, KnowledgeLayerId) else layer_id
        return next((layer for layer in self.layers if layer.id == normalized), None)


class EntityRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"ENT-{uuid4().hex[:12]}")
    name: str
    entity_type: str
    layer_ids: list[KnowledgeLayerId] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class KnowledgeClaim(BaseModel):
    id: str = Field(default_factory=lambda: f"CLM-{uuid4().hex[:12]}")
    text: str
    layer_ids: list[KnowledgeLayerId] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    source_memory_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    trust_level: TrustLevel = TrustLevel.UNKNOWN
    verification_status: str = "unverified"
    needs_verification: bool = True
    notes: str = ""

    @model_validator(mode="after")
    def verified_claims_need_evidence(self) -> "KnowledgeClaim":
        if self.verification_status == "verified" and not self.evidence_ids:
            raise ValueError("verified claims require at least one evidence id")
        return self


class RelationshipRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"REL-{uuid4().hex[:12]}")
    source_entity_id: str
    target_entity_id: str
    relationship_type: RelationshipType = RelationshipType.RELATED_TO
    summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class OpenQuestion(BaseModel):
    id: str = Field(default_factory=lambda: f"OQ-{uuid4().hex[:12]}")
    question: str
    layer_ids: list[KnowledgeLayerId] = Field(default_factory=list)
    reason: str = ""
    priority: int = Field(default=2, ge=1, le=5)
    suggested_actions: list[str] = Field(default_factory=list)
    resolved: bool = False


class SourceMemory(BaseModel):
    id: str = Field(default_factory=lambda: f"SM-{uuid4().hex[:12]}")
    source_id: str
    source_kind: str
    title: str = ""
    url: str | None = None
    summary: str
    use: SourceUse = SourceUse.CONTEXT
    trust_level: TrustLevel = TrustLevel.UNKNOWN
    evidence_ids: list[str] = Field(default_factory=list)
    related_layer_ids: list[KnowledgeLayerId] = Field(default_factory=list)
    extracted_entity_ids: list[str] = Field(default_factory=list)
    extracted_claim_ids: list[str] = Field(default_factory=list)
    keep_reason: str = ""
    filter_reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolAttempt(BaseModel):
    tool: str
    action: str
    query_or_input: str = ""
    observation: str = ""
    success: bool = True
    useful: bool = True
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskMemory(BaseModel):
    task_id: str = Field(default_factory=lambda: f"TASK-{uuid4().hex[:12]}")
    layer_id: KnowledgeLayerId | None = None
    objective: str
    checklist: list[str] = Field(default_factory=list)
    attempts: list[ToolAttempt] = Field(default_factory=list)
    local_reflections: list[str] = Field(default_factory=list)
    state_delta_summary: str = ""
    stop_reason: str = ""

    def compressed_reflection(self, max_chars: int = 600) -> str:
        failed = [attempt.query_or_input for attempt in self.attempts if not attempt.success or not attempt.useful]
        useful = [attempt.observation for attempt in self.attempts if attempt.success and attempt.useful]
        reflection = "；".join(self.local_reflections[-3:])
        parts = []
        if reflection:
            parts.append(f"反思：{reflection}")
        if failed:
            parts.append(f"低价值尝试：{', '.join(failed[-5:])}")
        if useful:
            parts.append(f"有效观察：{'；'.join(useful[-3:])}")
        text = " | ".join(parts)
        return text[:max_chars]


class SharedKnowledge(BaseModel):
    entities: list[EntityRecord] = Field(default_factory=list)
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    relationships: list[RelationshipRecord] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    source_memories: list[SourceMemory] = Field(default_factory=list)

    def accepted_claims(self) -> list[KnowledgeClaim]:
        return [
            claim for claim in self.claims
            if claim.verification_status in {"verified", "partially_verified", "unverified"}
            and claim.trust_level != TrustLevel.LOW
        ]


class AgentDecision(BaseModel):
    id: str = Field(default_factory=lambda: f"DEC-{uuid4().hex[:12]}")
    actor: str = "master_agent"
    action: AgentAction
    reason: str
    layer_id: KnowledgeLayerId | None = None
    next_task_ids: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ContextPack(BaseModel):
    pack_id: str = Field(default_factory=lambda: f"CTX-{uuid4().hex[:12]}")
    goal: str
    active_layer: KnowledgeLayer | None = None
    active_task: str = ""
    coverage_gaps: list[str] = Field(default_factory=list)
    entity_summaries: list[str] = Field(default_factory=list)
    claim_summaries: list[str] = Field(default_factory=list)
    evidence_summaries: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    working_memory_reflection: str = ""
    included_source_memory_ids: list[str] = Field(default_factory=list)
    excluded_source_memory_ids: list[str] = Field(default_factory=list)
    filter_notes: list[str] = Field(default_factory=list)

    def to_prompt_text(self) -> str:
        sections = [
            f"目标：{self.goal}",
            f"当前层：{self.active_layer.title if self.active_layer else '未指定'}",
            f"当前任务：{self.active_task or '未指定'}",
            f"覆盖缺口：{'；'.join(self.coverage_gaps) or '暂无'}",
            "实体：\n" + "\n".join(f"- {item}" for item in self.entity_summaries),
            "主张：\n" + "\n".join(f"- {item}" for item in self.claim_summaries),
            "证据：\n" + "\n".join(f"- {item}" for item in self.evidence_summaries),
            "待解决问题：\n" + "\n".join(f"- {item}" for item in self.open_questions),
        ]
        if self.working_memory_reflection:
            sections.append(f"工作记忆摘要：{self.working_memory_reflection}")
        return "\n\n".join(section for section in sections if section.strip())


class SectorBreakerState(BaseModel):
    state_version: str = "2"
    meta_context: MetaContext
    knowledge_schema: KnowledgeSchema
    shared_knowledge: SharedKnowledge = Field(default_factory=SharedKnowledge)
    evidence_refs: list[str] = Field(default_factory=list)
    working_memory: dict[str, TaskMemory] = Field(default_factory=dict)
    decision_log: list[AgentDecision] = Field(default_factory=list)
    human_feedback: list[str] = Field(default_factory=list)
    current_layer_id: KnowledgeLayerId | None = None
    current_task_id: str | None = None

    @classmethod
    def initialize(
        cls,
        *,
        project_id: str,
        domain: str,
        user_goal: str,
        market_scope: str = "mixed",
        source_policy: str = "reliable_first",
        include_prerequisite: bool = False,
    ) -> "SectorBreakerState":
        schema = KnowledgeSchema.default_for_domain(domain, include_prerequisite=include_prerequisite)
        return cls(
            meta_context=MetaContext(
                project_id=project_id,
                domain=domain,
                market_scope=market_scope,
                source_policy=source_policy,
                user_goal=user_goal,
                success_criteria=[
                    "生成可导入 Obsidian 的结构化知识库",
                    "关键事实带 evidence id",
                    "保留待验证问题和后续补库入口",
                ],
                safety_policies=[
                    "不输出违法或滥用操作指南",
                    "外部 AI 报告默认低可信，必须保留验证状态",
                ],
            ),
            knowledge_schema=schema,
            current_layer_id=schema.layers[0].id if schema.layers else None,
        )

    def add_task_memory(self, task: TaskMemory) -> None:
        self.working_memory[task.task_id] = task
        self.current_task_id = task.task_id
        if task.layer_id is not None:
            self.current_layer_id = task.layer_id

    def add_decision(self, decision: AgentDecision) -> None:
        self.decision_log.append(decision)

    def layer_coverage_gaps(self, layer_id: KnowledgeLayerId | str) -> list[str]:
        layer = self.knowledge_schema.layer(layer_id)
        if layer is None:
            return ["未知知识层"]
        gaps: list[str] = []
        if layer.coverage_status in {CoverageStatus.NOT_STARTED, CoverageStatus.NEEDS_MORE}:
            gaps.extend(layer.completion_criteria)
        for question in self.shared_knowledge.open_questions:
            if layer.id in question.layer_ids and not question.resolved:
                gaps.append(question.question)
        return list(dict.fromkeys(gaps))
