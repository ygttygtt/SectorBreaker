"""Knowledge Schema Planner — injects universal anchors, delegates extension layers to LLM."""
from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.agent_state.models import KnowledgeLayer, KnowledgeLayerId, KnowledgeSchema
from backend.app.agent_state.universal_anchors import UNIVERSAL_ANCHOR_IDS, build_universal_anchors
from backend.app.providers.interfaces import ChatMessage, LLMProvider


class PlannedLayer(BaseModel):
    id: str = ""
    title: str
    goal: str
    priority_weight: float = 1.0
    guiding_questions: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    required_evidence_types: list[str] = Field(default_factory=list)


class PlannedKnowledgeSchema(BaseModel):
    """LLM-proposed extension layers (universal anchors are NOT included here)."""
    layers: list[PlannedLayer]
    strategy: str | None = None
    generated_reason: str = ""


def _planned_layers_to_schema_layers(planned: list[PlannedLayer]) -> list[KnowledgeLayer]:
    result: list[KnowledgeLayer] = []
    for item in planned:
        raw_id = (item.id or "").strip()
        aliases = {
            KnowledgeLayerId.PREREQUISITE.value: KnowledgeLayerId.PREREQUISITE,
            KnowledgeLayerId.WHAT_WHY.value: KnowledgeLayerId.WHAT_WHY,
            KnowledgeLayerId.WHO.value: KnowledgeLayerId.WHO,
            KnowledgeLayerId.HOW.value: KnowledgeLayerId.HOW,
            KnowledgeLayerId.MONEY.value: KnowledgeLayerId.MONEY,
            KnowledgeLayerId.RISKS.value: KnowledgeLayerId.RISKS,
        }
        layer_id = aliases.get(raw_id, raw_id) or "custom_layer"
        result.append(KnowledgeLayer(
            id=layer_id,
            title=(item.title or str(layer_id)).strip()[:80],
            goal=item.goal.strip()[:500],
            priority_weight=item.priority_weight,
            guiding_questions=item.guiding_questions[:10],
            completion_criteria=item.completion_criteria[:10],
            required_evidence_types=item.required_evidence_types[:10],
        ))
    return result


async def build_adaptive_schema(
    *,
    domain: str,
    user_goal: str,
    market_scope: str,
    source_policy: str,
    llm_provider: LLMProvider | None,
) -> KnowledgeSchema:
    """Inject universal anchors first; LLM proposes domain-specific extension layers."""

    anchor_layers = build_universal_anchors(domain)

    def _default_extensions() -> list[KnowledgeLayer]:
        fallback = KnowledgeSchema.default_for_domain(domain, include_prerequisite=False)
        return [
            layer for layer in fallback.layers
            if (layer.id.value if hasattr(layer.id, "value") else str(layer.id))
            not in UNIVERSAL_ANCHOR_IDS
        ]

    if llm_provider is None:
        return KnowledgeSchema(
            domain=domain,
            strategy="universal_anchors_with_default_extensions",
            layers=anchor_layers + _default_extensions(),
            generated_reason="No LLM configured; using universal anchors + default extension layers.",
        )

    prompt = (
        "You are SectorBreaker's Knowledge Schema Planner.\n"
        "Three universal anchor layers are already fixed: 本源与边界, 参与者生态, 运行机制.\n"
        "Your task: propose 2 to 4 domain-specific EXTENSION layers that complement the anchors.\n\n"
        "Design principles:\n"
        "- Technical domains: add tool ecosystem, prerequisites, advanced implementation layers;\n"
        "- Business/market domains: add value flow, channels, pricing/monetization layers;\n"
        "- Policy/compliance domains: add regulatory history, enforcement, compliance cost layers;\n"
        "- Academic/open-source: skip commercial incentives, use contributor ecology instead;\n"
        "- completion_criteria must be specific and usable for coverage evaluation;\n"
        "- required_evidence_types: use official_doc, tutorial, case, pricing, policy, etc.\n\n"
        f"Domain: {domain}\nUser goal: {user_goal}\nMarket scope: {market_scope}\n"
        f"Source policy: {source_policy}\n\n"
        "Output PlannedKnowledgeSchema JSON with only extension layers (2-4), NOT the universal anchors."
    )
    try:
        planned = await llm_provider.complete_structured(
            [ChatMessage(role="user", content=prompt)],
            PlannedKnowledgeSchema,
        )
    except Exception:
        return KnowledgeSchema(
            domain=domain,
            strategy="universal_anchors_with_default_extensions",
            layers=anchor_layers + _default_extensions(),
            generated_reason="LLM extension layer planning failed; using default extensions.",
        )

    extension_layers = _planned_layers_to_schema_layers(planned.layers)
    extension_layers = [
        layer for layer in extension_layers
        if (layer.id.value if hasattr(layer.id, "value") else str(layer.id))
        not in UNIVERSAL_ANCHOR_IDS
    ]
    if not extension_layers:
        extension_layers = _default_extensions()

    return KnowledgeSchema(
        domain=domain,
        strategy=planned.strategy or "universal_anchors_with_llm_extensions",
        layers=anchor_layers + extension_layers,
        generated_reason=planned.generated_reason[:1200],
    )
