import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.context import KernelContextBuilder
from backend.app.agent_kernel.models import AgentActionType, AgentDecision, KernelLoopConfig, KernelObservation, KernelRunStatus, KernelStateDelta, ToolCall
from backend.app.agent_kernel.runtime import AgentKernelRuntime
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry
from backend.app.agent_state import SectorBreakerState
from backend.app.schemas import Artifact, ArtifactType, MarketScope, ProjectStatus, ResearchDepth, ResearchProject, SourcePolicy


def _project() -> ResearchProject:
    return ResearchProject(
        id="project-kernel",
        title="API中转站",
        domain="API中转站",
        market_scope=MarketScope.MIXED,
        source_policy=SourcePolicy.OPEN_WEB,
        depth=ResearchDepth.QUICK,
        status=ProjectStatus.DRAFT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_agent_kernel_runtime_follows_llm_decided_tool_order() -> None:
    class FakePolicy:
        def __init__(self) -> None:
            self.index = 0
            self.decisions = [
                AgentDecision(
                    thought_summary="先写一篇 L1 文档验证工具链。",
                    action_type=AgentActionType.WRITE_ARTIFACT,
                    tool_call=ToolCall(
                        tool_name="write_layer_document",
                        args={"layer_id": "L1_what_why", "title": "L1 本源与需求", "writing_goal": "解释是什么和为什么"},
                        reason="当前测试直接验证写作工具。",
                    ),
                ),
                AgentDecision(
                    thought_summary="已有文档，可以结束。",
                    action_type=AgentActionType.FINISH,
                    stop_reason="测试完成",
                ),
            ]

        async def decide(self, **kwargs):
            decision = self.decisions[self.index]
            self.index += 1
            return decision

    class FakeRepository:
        def list_evidence(self, project_id):
            return []

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

    async def fake_write(tool_call, context):
        artifact = Artifact(
            id="ART-1",
            project_id=context.project.id,
            artifact_type=ArtifactType.DOMAIN_OVERVIEW,
            title="L1 本源与需求",
            content_path="01-L1-本源与需求.md",
            content="# L1 本源与需求\n\n## 是什么\n\n测试内容，证据：EV-1。",
            source_evidence_ids=["EV-1"],
            schema_version="v2-agent-kernel",
            created_at=datetime.now(UTC),
        )
        context.artifacts.append(artifact)
        from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta

        return KernelObservation(
            tool_name="write_layer_document",
            success=True,
            summary="写作完成",
            state_delta=KernelStateDelta(artifact_ids=[artifact.id]),
            artifact_ids=[artifact.id],
        )

    events = []

    async def emit(event):
        events.append(event)

    registry = ToolRegistry()
    from backend.app.agent_kernel.models import ToolSpec

    registry.register(ToolSpec(name="write_layer_document", description="fake"), fake_write)
    state = SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库")
    context = KernelRuntimeContext(
        project=_project(),
        repository=FakeRepository(),  # type: ignore[arg-type]
        state=state,
        search_provider=None,
        llm_provider=None,
        emit_event=emit,
    )
    result = asyncio.run(AgentKernelRuntime(policy=FakePolicy(), registry=registry).run(context))  # type: ignore[arg-type]

    assert result.status == "completed"
    assert result.artifact_ids == ["ART-1"]
    assert any(event.gate == "agent_decide" for event in events)
    assert any(event.gate == "tool_execution" for event in events)
    assert any(event.gate == "state_update" for event in events)


def test_agent_kernel_runtime_main_writer_failure_continues_to_finish() -> None:
    """V3 behavior: main writer failure does NOT immediately kill the run.

    The loop continues to the next policy decision (FINISH). Since there are
    no artifacts, the runtime returns BLOCKED. This is intentional — it gives
    the Agent a chance to retry or switch strategy before being killed.
    """

    class FakePolicy:
        def __init__(self) -> None:
            self.index = 0
            self.decisions = [
                AgentDecision(
                    thought_summary="尝试写 L1 文档。",
                    action_type=AgentActionType.WRITE_ARTIFACT,
                    tool_call=ToolCall(
                        tool_name="write_layer_document",
                        args={"layer_id": "L1_what_why", "title": "L1 本源与需求", "writing_goal": "解释是什么"},
                        reason="验证写作失败会被记录但不立即中断。",
                    ),
                ),
                AgentDecision(
                    thought_summary="写作失败，选择结束。",
                    action_type=AgentActionType.FINISH,
                    stop_reason="没有产物可继续",
                ),
            ]

        async def decide(self, **kwargs):
            decision = self.decisions[self.index]
            self.index += 1
            return decision

    class FakeRepository:
        def list_evidence(self, project_id):
            return []

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

    async def failing_write(tool_call, context):
        return KernelObservation(
            tool_name="write_layer_document",
            success=False,
            summary="LLM 写作连续失败，未保存产物。",
            error="llm writing failed after retries",
        )

    events = []

    async def emit(event):
        events.append(event)

    registry = ToolRegistry()
    from backend.app.agent_kernel.models import ToolSpec

    registry.register(ToolSpec(name="write_layer_document", description="fake"), failing_write)
    state = SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库")
    context = KernelRuntimeContext(
        project=_project(),
        repository=FakeRepository(),  # type: ignore[arg-type]
        state=state,
        search_provider=None,
        llm_provider=None,
        emit_event=emit,
    )
    policy = FakePolicy()
    result = asyncio.run(AgentKernelRuntime(policy=policy, registry=registry).run(context))  # type: ignore[arg-type]

    # V3: 主文档失败不再立即 FAILED，而是记录后继续到 FINISH。
    # 没有产物 → BLOCKED（有产物时则 COMPLETED 或 MAX_ITERATIONS）。
    assert result.status == KernelRunStatus.BLOCKED
    assert result.artifact_ids == []
    assert policy.index == 2  # 两个决策都执行了（写文档 + FINISH）
    # 写作失败事件仍然被记录（severity="error" 对主文档）
    assert any(event.gate == "artifact_writing" and event.severity == "error" for event in events)


def test_agent_kernel_runtime_executes_ordered_tool_calls_and_updates_state_between_tools() -> None:
    class FakePolicy:
        def __init__(self) -> None:
            self.index = 0
            self.decisions = [
                AgentDecision(
                    thought_summary="先评估覆盖，再记录反思。",
                    action_type=AgentActionType.CALL_TOOL,
                    current_goal="确认 L1 是否可写",
                    plan_steps=["评估覆盖", "记录反思"],
                    progress_check="State 还没有覆盖评分。",
                    tool_calls=[
                        ToolCall(
                            tool_name="evaluate_coverage",
                            args={"layer_id": "L1_what_why"},
                            reason="先让 State 产生覆盖评分。",
                        ),
                        ToolCall(
                            tool_name="reflect_on_progress",
                            args={"reflection": "覆盖不足，下一轮应补搜定义和需求场景。"},
                            reason="根据覆盖评分更新工作记忆。",
                        ),
                    ],
                ),
                AgentDecision(
                    thought_summary="测试结束。",
                    action_type=AgentActionType.BLOCK,
                    stop_reason="测试主动停止",
                ),
            ]

        async def decide(self, **kwargs):
            decision = self.decisions[self.index]
            self.index += 1
            return decision

    class FakeRepository:
        def list_evidence(self, project_id):
            return []

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

    seen_scores = []

    async def fake_evaluate(tool_call, context):
        return KernelObservation(
            tool_name="evaluate_coverage",
            success=True,
            summary="覆盖评估完成",
            state_delta=KernelStateDelta(coverage_updates=[{
                "layer_id": "L1_what_why",
                "coverage_score": 0.25,
                "coverage_status": "needs_more",
                "coverage_notes": "测试覆盖不足",
            }]),
        )

    async def fake_reflect(tool_call, context):
        layer = context.state.knowledge_schema.layer("L1_what_why")
        seen_scores.append(layer.coverage_score if layer else None)
        return KernelObservation(
            tool_name="reflect_on_progress",
            success=True,
            summary="阶段反思完成",
            state_delta=KernelStateDelta(phase_reflection="覆盖不足，下一轮应补搜定义和需求场景。"),
        )

    events = []

    async def emit(event):
        events.append(event)

    registry = ToolRegistry()
    from backend.app.agent_kernel.models import ToolSpec

    registry.register(ToolSpec(name="evaluate_coverage", description="fake"), fake_evaluate)
    registry.register(ToolSpec(name="reflect_on_progress", description="fake"), fake_reflect)
    state = SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库")
    context = KernelRuntimeContext(
        project=_project(),
        repository=FakeRepository(),  # type: ignore[arg-type]
        state=state,
        search_provider=None,
        llm_provider=None,
        emit_event=emit,
    )
    result = asyncio.run(AgentKernelRuntime(policy=FakePolicy(), registry=registry).run(context))  # type: ignore[arg-type]

    assert result.status == KernelRunStatus.BLOCKED
    assert seen_scores == [0.25]
    # V3: action event message 不再以 "Action:" 开头（改用 user_notice 或 tool_name），
    # 用 agent="V3 Tool Executor" 过滤 ACTION 事件（区别于 OBSERVATION 事件的 agent=tool_name）。
    action_agents = [
        event.agent for event in events
        if event.gate == "tool_execution" and event.agent == "V3 Tool Executor"
    ]
    assert action_agents == ["V3 Tool Executor", "V3 Tool Executor"]
    assert any("coverage_updates+1" in event.message for event in events)


def test_kernel_context_includes_artifact_memory() -> None:
    state = SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库")
    artifact = Artifact(
        id="ART-KERNEL-L1-1",
        project_id="project-kernel",
        artifact_type=ArtifactType.DOMAIN_OVERVIEW,
        title="API 中转站本源",
        content_path="01-api.md",
        content="# API 中转站本源\n\n## 核心结论\n\n这是测试正文。",
        source_evidence_ids=["EV-KERNEL-1"],
        schema_version="v2-agent-kernel",
        created_at=datetime.now(UTC),
    )

    context = KernelContextBuilder().build_prompt_context(
        state=state,
        tools=[],
        trace_tail=[],
        artifacts=[artifact],
    )

    assert "## Artifact Memory" in context
    assert '"artifact_count": 1' in context
    assert "API 中转站本源" in context


def test_agent_kernel_runtime_hard_blocks_search_past_budget() -> None:
    class SearchTwicePolicy:
        async def decide(self, **kwargs):
            return AgentDecision(
                thought_summary="执行两次搜索验证硬预算。",
                action_type=AgentActionType.CALL_TOOL,
                tool_calls=[
                    ToolCall(tool_name="search_web", args={"query": "first"}, reason="first"),
                    ToolCall(tool_name="search_web", args={"query": "second"}, reason="second"),
                ],
            )

    class FakeRepository:
        def list_evidence(self, project_id):
            return []

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

    dispatched: list[str] = []

    async def fake_search(tool_call, context):
        dispatched.append(tool_call.args["query"])
        context.search_call_count += 1
        return KernelObservation(tool_name="search_web", success=True, summary="searched")

    registry = ToolRegistry()
    from backend.app.agent_kernel.models import ToolSpec

    registry.register(ToolSpec(name="search_web", description="fake"), fake_search)
    state = SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库")
    context = KernelRuntimeContext(
        project=_project(),
        repository=FakeRepository(),  # type: ignore[arg-type]
        state=state,
        search_provider=None,
        llm_provider=None,
        emit_event=lambda event: asyncio.sleep(0),
    )

    result = asyncio.run(AgentKernelRuntime(
        policy=SearchTwicePolicy(),  # type: ignore[arg-type]
        registry=registry,
        config=KernelLoopConfig(max_iterations=2, max_search_calls=1, max_writer_calls=1),
    ).run(context))

    assert result.status == KernelRunStatus.WAITING_FOR_HUMAN
    assert dispatched == ["first"]
    assert any("search budget exhausted" in (event.data.get("error") or "") for event in result.trace)
