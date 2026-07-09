from backend.app.agent_kernel.models import AgentActionType, AgentDecision, ToolCall


def test_agent_decision_requires_tool_call_for_call_tool() -> None:
    decision = AgentDecision(
        thought_summary="需要先搜索 API 中转站的需求来源。",
        action_type=AgentActionType.CALL_TOOL,
        tool_call=ToolCall(
            tool_name="search_web",
            args={"query": "API中转站 是什么 需求 痛点"},
            reason="L1 缺少本源与需求信息。",
        ),
        expected_observation="获得定义、需求和使用场景线索。",
    )

    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "search_web"


def test_agent_decision_accepts_user_notice() -> None:
    decision = AgentDecision(
        thought_summary="L1 coverage_score 足够，准备写作。",
        user_notice="我已经收集够资料了，现在开始撰写这个领域的入门介绍。",
        action_type=AgentActionType.WRITE_ARTIFACT,
        tool_call=ToolCall(tool_name="write_layer_document", args={"title": "本源与边界"}, reason="x"),
    )

    assert decision.user_notice.startswith("我")


def test_agent_decision_user_notice_defaults_empty() -> None:
    decision = AgentDecision(
        thought_summary="finish",
        action_type=AgentActionType.FINISH,
        stop_reason="done",
    )

    assert decision.user_notice == ""
