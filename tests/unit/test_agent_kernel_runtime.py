import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.models import AgentActionType, AgentDecision, KernelObservation, KernelRunStatus, ToolCall
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
