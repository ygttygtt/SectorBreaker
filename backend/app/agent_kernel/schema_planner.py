"""Domain-adaptive KnowledgeSchema planning for the Agent Kernel."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from backend.app.agent_state.models import KnowledgeLayer, KnowledgeLayerId, KnowledgeSchema
from backend.app.providers.interfaces import ChatMessage, LLMProvider


class PlannedLayer(BaseModel):
    id: str
    title: str
    goal: str
    priority_weight: float = Field(default=1.0, ge=0.0, le=5.0)
    prerequisite_layer_ids: list[str] = Field(default_factory=list)
    guiding_questions: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    required_evidence_types: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def clean_id(cls, value: str) -> str:
        cleaned = value.strip().replace(" ", "_")
        if not cleaned:
            raise ValueError("layer id cannot be empty")
        return cleaned[:80]


class PlannedKnowledgeSchema(BaseModel):
    strategy: str = "llm_adaptive_practical_cognition"
    generated_reason: str
    layers: list[PlannedLayer]


async def build_adaptive_schema(
    *,
    domain: str,
    user_goal: str,
    market_scope: str,
    source_policy: str,
    llm_provider: LLMProvider | None,
) -> KnowledgeSchema:
    """Ask the LLM for a domain-fit cognition schema, with strict fallback."""

    fallback = KnowledgeSchema.default_for_domain(domain, include_prerequisite=False)
    if llm_provider is None:
        fallback.generated_reason = "未配置 LLM，使用默认实战认知模型作为可执行 fallback。"
        return fallback

    prompt = (
        "你是 SectorBreaker 的知识 Schema Planner。请为一个领域建库 Agent 生成领域自适应知识层级。\n"
        "重要原则：L1-L5 只是参考认知模型，不是必须逐层固定执行。你可以保留通用层，也可以根据领域增加、拆分或调整重点。\n"
        "每层要服务于最终生成 Obsidian 知识库，并能指导后续 Agent 判断还缺什么信息。\n\n"
        f"领域：{domain}\n"
        f"用户目标：{user_goal}\n"
        f"市场范围：{market_scope}\n"
        f"信源策略：{source_policy}\n\n"
        "请输出 PlannedKnowledgeSchema JSON，要求：\n"
        "- layers 数量 4 到 8 个；\n"
        "- 至少包含一个解释“是什么/为什么存在”的本源层；\n"
        "- 至少包含一个“玩家/角色/生态”或同义层；\n"
        "- 至少包含一个“机制/实现/操作/方法”或同义层；\n"
        "- 至少包含一个“风险/边界/限制”或同义层；\n"
        "- 对技术型领域，提高实现、工具、前置概念层权重；\n"
        "- 对市场/行业型领域，提高玩家、价值流、渠道/供应链层权重；\n"
        "- completion_criteria 必须能用于覆盖度评估，不要写空泛口号；\n"
        "- required_evidence_types 写具体证据类型，例如 official_doc、tutorial、case、pricing、policy、community_discussion。\n"
    )
    try:
        planned = await llm_provider.complete_structured(
            [ChatMessage(role="user", content=prompt)],
            PlannedKnowledgeSchema,
        )
    except Exception:
        fallback.generated_reason = "LLM 自适应 Schema 规划失败，使用默认实战认知模型作为安全 fallback。"
        return fallback

    layers = _planned_layers_to_schema_layers(planned.layers)
    if len(layers) < 3:
        fallback.generated_reason = "LLM 自适应 Schema 层级过少，使用默认实战认知模型作为安全 fallback。"
        return fallback
    return KnowledgeSchema(
        domain=domain,
        strategy=planned.strategy or "llm_adaptive_practical_cognition",
        layers=layers,
        generated_reason=planned.generated_reason[:1200],
    )


def _planned_layers_to_schema_layers(planned_layers: list[PlannedLayer]) -> list[KnowledgeLayer]:
    layers: list[KnowledgeLayer] = []
    seen_ids: set[str] = set()
    for planned in planned_layers[:8]:
        layer_id = _normalize_legacy_id(planned.id)
        layer_key = layer_id.value if hasattr(layer_id, "value") else str(layer_id)
        if layer_key in seen_ids:
            continue
        seen_ids.add(layer_key)
        layers.append(KnowledgeLayer(
            id=layer_id,
            title=planned.title.strip()[:80] or str(layer_id),
            goal=planned.goal.strip()[:500],
            priority_weight=planned.priority_weight,
            prerequisite_layer_ids=[_normalize_legacy_id(item) for item in planned.prerequisite_layer_ids],
            guiding_questions=planned.guiding_questions[:10],
            completion_criteria=planned.completion_criteria[:10],
            required_evidence_types=planned.required_evidence_types[:10],
        ))
    return layers


def _normalize_legacy_id(layer_id: str) -> KnowledgeLayerId | str:
    aliases = {
        KnowledgeLayerId.PREREQUISITE.value: KnowledgeLayerId.PREREQUISITE,
        KnowledgeLayerId.WHAT_WHY.value: KnowledgeLayerId.WHAT_WHY,
        KnowledgeLayerId.WHO.value: KnowledgeLayerId.WHO,
        KnowledgeLayerId.HOW.value: KnowledgeLayerId.HOW,
        KnowledgeLayerId.MONEY.value: KnowledgeLayerId.MONEY,
        KnowledgeLayerId.RISKS.value: KnowledgeLayerId.RISKS,
    }
    cleaned = layer_id.strip()
    return aliases.get(cleaned, cleaned)
