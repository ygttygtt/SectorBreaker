import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.reducer import apply_state_delta
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.artifacts import write_layer_document
from backend.app.agent_kernel.tools.state import evaluate_coverage, internalize_observation, manage_state_memory, reflect_on_progress
from backend.app.agent_state import KnowledgeClaim, SectorBreakerState, SourceMemory
from backend.app.schemas import MarketScope, ProjectStatus, ResearchDepth, ResearchProject, SourcePolicy


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


def test_write_layer_document_retries_and_does_not_save_artifact_when_llm_fails() -> None:
    class FailingLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, messages):
            self.calls += 1
            raise ValueError("broken llm response")

        async def complete_structured(self, messages, response_schema):
            raise AssertionError("Markdown writing must not use structured completion")

    class FakeRepository:
        def list_evidence(self, project_id):
            return []

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

    events = []

    async def emit(event):
        events.append(event)

    llm = FailingLLM()
    context = KernelRuntimeContext(
        project=_project(),
        repository=FakeRepository(),  # type: ignore[arg-type]
        state=SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库"),
        search_provider=None,
        llm_provider=llm,  # type: ignore[arg-type]
        emit_event=emit,
    )

    observation = asyncio.run(write_layer_document(
        ToolCall(
            tool_name="write_layer_document",
            args={"layer_id": "L1_what_why", "title": "L1 本源与需求", "writing_goal": "解释是什么"},
            reason="测试失败不落模板。",
        ),
        context,
    ))

    assert observation.success is False
    assert observation.artifact_ids == []
    assert context.artifacts == []
    assert llm.calls == 2
    assert observation.data["attempts"] == 2
    assert "LLM 分节写作失败" in observation.summary


def test_state_tools_create_drill_down_and_manage_memory() -> None:
    class FakeRepository:
        def list_evidence(self, project_id):
            return []

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

    async def emit(event):
        return None

    state = SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库")
    state.shared_knowledge.source_memories.append(SourceMemory(
        source_id="SRC-1",
        source_kind="search",
        title="重复营销文",
        summary="低价值重复营销内容",
    ))
    state.shared_knowledge.claims.append(KnowledgeClaim(
        id="CLM-1",
        text="旧说法",
        layer_ids=["L1_what_why"],
        confidence=0.3,
    ))
    context = KernelRuntimeContext(
        project=_project(),
        repository=FakeRepository(),  # type: ignore[arg-type]
        state=state,
        search_provider=None,
        llm_provider=None,
        emit_event=emit,
    )

    observation = asyncio.run(internalize_observation(
        ToolCall(
            tool_name="internalize_observation",
            args={
                "summary": "发现反向代理是读者盲区。",
                "drill_down_tasks": [{
                    "question": "反向代理是什么？",
                    "concept_or_entity": "反向代理",
                    "parent_layer_id": "L3_how",
                    "priority": 4,
                }],
            },
            reason="创建下钻任务。",
        ),
        context,
    ))
    context.state = apply_state_delta(context.state, observation.state_delta, decision=_fake_decision(), observation=observation)

    layer = context.state.knowledge_schema.layer("L3_how")
    assert layer is not None
    assert len(layer.drill_down_task_ids) == 1
    assert context.state.shared_knowledge.open_questions[0].status == "drill_down"

    coverage = asyncio.run(evaluate_coverage(
        ToolCall(tool_name="evaluate_coverage", args={"layer_id": "L3_how"}, reason="评估覆盖。"),
        context,
    ))
    assert coverage.success is True
    assert coverage.state_delta.coverage_updates[0]["layer_id"] == "L3_how"

    managed = asyncio.run(manage_state_memory(
        ToolCall(
            tool_name="manage_state_memory",
            args={
                "hidden_source_ids": ["SRC-1"],
                "claim_updates": [{
                    "id": "CLM-1",
                    "text": "新说法",
                    "confidence": 0.8,
                    "revision_reason": "被新材料修正",
                }],
                "reason": "清理重复来源并修正旧主张。",
            },
            reason="治理 State。",
        ),
        context,
    ))
    context.state = apply_state_delta(context.state, managed.state_delta, decision=_fake_decision(), observation=managed)

    assert context.state.shared_knowledge.source_memories[0].hidden_from_context is True
    assert context.state.shared_knowledge.claims[0].text == "新说法"
    assert context.state.shared_knowledge.claims[0].confidence == 0.8


def test_reflect_on_progress_updates_task_memory() -> None:
    from backend.app.agent_state import TaskMemory

    class FakeRepository:
        def list_evidence(self, project_id):
            return []

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

    async def emit(event):
        return None

    state = SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库")
    task = TaskMemory(layer_id="L1_what_why", objective="理解本源")
    state.add_task_memory(task)
    context = KernelRuntimeContext(
        project=_project(),
        repository=FakeRepository(),  # type: ignore[arg-type]
        state=state,
        search_provider=None,
        llm_provider=None,
        emit_event=emit,
    )

    observation = asyncio.run(reflect_on_progress(
        ToolCall(
            tool_name="reflect_on_progress",
            args={"reflection": "当前搜索太泛，需要补需求场景。", "next_steps": ["搜索真实用户场景"]},
            reason="反思搜索策略。",
        ),
        context,
    ))

    assert observation.success is True
    assert task.memory_summary == "当前搜索太泛，需要补需求场景。"
    assert "搜索真实用户场景" in task.checklist


def _fake_decision():
    from backend.app.agent_kernel.models import AgentActionType, AgentDecision

    return AgentDecision(
        thought_summary="测试决策",
        action_type=AgentActionType.CALL_TOOL,
        tool_call=ToolCall(tool_name="update_task_state", args={}, reason="测试"),
    )
