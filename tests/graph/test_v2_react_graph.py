from backend.app.agent_state.models import SectorBreakerState, SourceMemory, SourceUse, TrustLevel
from backend.app.graph.v2_react_graph import build_v2_react_graph, route_after_coverage


def test_v2_react_graph_exports_when_state_has_partial_material() -> None:
    sector_state = SectorBreakerState.initialize(
        project_id="p1",
        domain="量化投资",
        user_goal="生成可扩展知识库",
    )
    sector_state.shared_knowledge.source_memories.append(SourceMemory(
        source_id="doc-1",
        source_kind="assistant_brief",
        title="DeepSearch 报告",
        summary="量化投资涉及股票、回测、滑点、风险控制和交易成本。",
        use=SourceUse.CONTEXT,
        trust_level=TrustLevel.LOW,
    ))

    graph = build_v2_react_graph()
    result = graph.invoke({"sector_state": sector_state.model_dump(mode="json")})

    assert result["exported"] is True
    decisions = result["sector_state"]["decision_log"]
    assert any(item["action"] == "dispatch_task" for item in decisions)
    assert any(item["action"] == "degrade" for item in decisions)


def test_v2_route_after_coverage_can_loop_or_wait_for_user() -> None:
    assert route_after_coverage({"next_action": "search_again"}) == "master_plan"
    assert route_after_coverage({"next_action": "ask_user"}) == "wait_for_human_feedback"
    assert route_after_coverage({"next_action": "continue"}) == "write_knowledge_base"
