from backend.app.agent_state.models import AgentAction, KnowledgeLayerId
from backend.app.agents.react_loop import (
    BoundedReActRunner,
    Observation,
    ReActStep,
    StateDelta,
    ThoughtSummary,
    ToolCallRequest,
)


def test_bounded_react_runner_executes_tool_and_stops_when_sufficient() -> None:
    async def policy(steps):
        if not steps:
            return ReActStep(
                thought=ThoughtSummary(text="我需要先搜索玩家信息。"),
                tool_call=ToolCallRequest(tool="search", action="query", query="量化投资 主流公司"),
                state_delta=StateDelta(notes=["准备搜索 L2 玩家"]),
                decision=AgentAction.SEARCH_AGAIN,
            )
        return ReActStep(
            thought=ThoughtSummary(text="已经找到主流公司，可以停止。"),
            state_delta=StateDelta(entity_ids=["ENT-1"]),
            decision=AgentAction.CONTINUE,
        )

    async def dispatch(tool_call):
        return Observation(tool=tool_call.tool, summary="找到若干量化私募和券商资管。", evidence_ids=["EV-1"])

    import asyncio

    result = asyncio.run(
        BoundedReActRunner(max_steps=3).run(
            task_id="task-1",
            layer_id=KnowledgeLayerId.WHO,
            policy=policy,
            tool_dispatcher=dispatch,
        )
    )

    assert len(result.steps) == 2
    assert result.steps[0].observation is not None
    assert result.state_delta.entity_ids == ["ENT-1"]
    assert result.stop_reason == "sufficient"


def test_bounded_react_runner_stops_at_max_steps() -> None:
    async def policy(steps):
        return ReActStep(
            thought=ThoughtSummary(text="还需要继续搜索。"),
            tool_call=ToolCallRequest(tool="search", action="query", query=f"query-{len(steps)}"),
            decision=AgentAction.SEARCH_AGAIN,
        )

    async def dispatch(tool_call):
        return Observation(tool=tool_call.tool, summary="结果仍然不足。", useful=False)

    import asyncio

    result = asyncio.run(
        BoundedReActRunner(max_steps=2).run(
            task_id="task-loop",
            policy=policy,
            tool_dispatcher=dispatch,
        )
    )

    assert len(result.steps) == 2
    assert result.stop_reason == "max_steps"
