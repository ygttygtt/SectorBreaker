import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.context import KernelContextBuilder
from backend.app.agent_kernel.models import AgentActionType, AgentDecision, KernelObservation, KernelRunStatus, KernelStateDelta, ToolCall
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


def test_agent_kernel_runtime_stops_on_document_writing_failure() -> None:
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
                        reason="验证写作失败必须中断。",
                    ),
                ),
                AgentDecision(
                    thought_summary="不应该走到这里。",
                    action_type=AgentActionType.FINISH,
                    stop_reason="错误地继续 finish",
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

    assert result.status == KernelRunStatus.FAILED
    assert result.artifact_ids == []
    assert result.stop_reason == "artifact_writing_failed"
    assert policy.index == 1
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
    assert [
        event.agent for event in events
        if event.gate == "tool_execution" and event.message.startswith("Action:")
    ] == ["V2 Tool Executor", "V2 Tool Executor"]
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
