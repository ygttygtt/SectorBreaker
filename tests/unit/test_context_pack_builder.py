from backend.app.agent_state import ContextPackBuilder
from backend.app.agent_state.models import (
    EntityRecord,
    KnowledgeClaim,
    KnowledgeLayerId,
    SectorBreakerState,
    SourceMemory,
    SourceUse,
    TrustLevel,
)


def test_context_pack_keeps_relevant_claims_and_filters_noise() -> None:
    state = SectorBreakerState.initialize(project_id="p1", domain="大模型 API 中转站", user_goal="生成知识库")
    state.shared_knowledge.entities.append(EntityRecord(
        name="号池",
        entity_type="concept",
        layer_ids=[KnowledgeLayerId.HOW],
        summary="用于描述多账号资源池的领域术语。",
    ))
    state.shared_knowledge.claims.append(KnowledgeClaim(
        text="中转站通常需要模型 API、网关服务、计费系统和风控策略。",
        layer_ids=[KnowledgeLayerId.HOW],
        evidence_ids=["EV-1"],
        trust_level=TrustLevel.MEDIUM,
        verification_status="partially_verified",
    ))
    state.shared_knowledge.source_memories.extend([
        SourceMemory(
            id="SM-good",
            source_id="EV-1",
            source_kind="search",
            title="中转站架构说明",
            summary="大模型 API 中转站涉及 API 网关、模型供应商、用量计费、密钥管理和风控。",
            use=SourceUse.EVIDENCE,
            trust_level=TrustLevel.MEDIUM,
            evidence_ids=["EV-1"],
            related_layer_ids=[KnowledgeLayerId.HOW],
        ),
        SourceMemory(
            id="SM-noise",
            source_id="noise",
            source_kind="search",
            title="导航噪音",
            summary="Skip to content Sign in Navigation cookie loading",
            use=SourceUse.CONTEXT,
            related_layer_ids=[KnowledgeLayerId.HOW],
        ),
        SourceMemory(
            id="SM-risk",
            source_id="risk-only",
            source_kind="search",
            title="风险文章",
            summary="监管和封号风险需要放到风险边界层。",
            use=SourceUse.EVIDENCE,
            related_layer_ids=[KnowledgeLayerId.RISKS],
        ),
    ])

    pack = ContextPackBuilder().build(
        state,
        layer_id=KnowledgeLayerId.HOW,
        active_task="拆解中转站实现架构",
    )

    assert any("号池" in item for item in pack.entity_summaries)
    assert any("API 网关" in item for item in pack.evidence_summaries)
    assert len(pack.included_source_memory_ids) == 1
    assert "SM-noise" in pack.excluded_source_memory_ids
    assert "SM-risk" in pack.excluded_source_memory_ids
    assert "Skip to content" not in pack.to_prompt_text()
