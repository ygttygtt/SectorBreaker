import pytest

from backend.app.agent_state.models import (
    AgentAction,
    AgentDecision,
    CoverageStatus,
    KnowledgeClaim,
    KnowledgeLayerId,
    SectorBreakerState,
    TaskMemory,
    ToolAttempt,
)


def test_sectorbreaker_state_initializes_dynamic_practical_schema() -> None:
    state = SectorBreakerState.initialize(
        project_id="p1",
        domain="大模型 API 中转站",
        user_goal="构建可持续扩展的 Obsidian 领域知识库",
        include_prerequisite=True,
    )

    layer_ids = [layer.id for layer in state.knowledge_schema.layers]
    assert layer_ids[0] == KnowledgeLayerId.PREREQUISITE
    assert KnowledgeLayerId.WHAT_WHY in layer_ids
    assert KnowledgeLayerId.HOW in layer_ids
    assert KnowledgeLayerId.MONEY in layer_ids
    assert KnowledgeLayerId.RISKS in layer_ids
    assert state.meta_context.safety_policies
    assert state.current_layer_id == KnowledgeLayerId.PREREQUISITE


def test_verified_claim_requires_evidence_ids() -> None:
    with pytest.raises(ValueError):
        KnowledgeClaim(text="这是已验证事实", verification_status="verified")

    claim = KnowledgeClaim(
        text="RAG 常用于企业知识库问答。",
        verification_status="verified",
        evidence_ids=["EV-1"],
    )
    assert claim.evidence_ids == ["EV-1"]


def test_task_memory_compresses_failed_attempts_and_reflections() -> None:
    task = TaskMemory(
        objective="理解号池是什么",
        layer_id=KnowledgeLayerId.HOW,
        local_reflections=["第一次搜索只有营销噪音，需要换成风险/防坑视角。"],
        attempts=[
            ToolAttempt(tool="search", action="query", query_or_input="号池 教程", success=True, useful=False),
            ToolAttempt(tool="search", action="query", query_or_input="号池 风险 防坑", observation="结果提到账号来源和平台封禁风险。"),
        ],
    )

    reflection = task.compressed_reflection()
    assert "低价值尝试" in reflection
    assert "号池 教程" in reflection
    assert "平台封禁风险" in reflection


def test_state_records_decisions_and_layer_gaps() -> None:
    state = SectorBreakerState.initialize(project_id="p1", domain="量化投资", user_goal="生成知识库")
    decision = AgentDecision(action=AgentAction.SEARCH_AGAIN, reason="L1 仍缺少基础解释")

    state.add_decision(decision)
    gaps = state.layer_coverage_gaps(KnowledgeLayerId.WHAT_WHY)

    assert state.decision_log[0].action == AgentAction.SEARCH_AGAIN
    assert gaps
    assert state.knowledge_schema.layer(KnowledgeLayerId.WHAT_WHY).coverage_status == CoverageStatus.NOT_STARTED
