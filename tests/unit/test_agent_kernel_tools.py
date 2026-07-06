import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.artifacts import write_layer_document
from backend.app.agent_state import SectorBreakerState
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
