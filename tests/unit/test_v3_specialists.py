import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.specialists import SpecialistResult, SpecialistRole, SpecialistTask
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.specialists import delegate_specialists
from backend.app.agent_state import SectorBreakerState
from backend.app.schemas import MarketScope, ProjectStatus, ResearchDepth, ResearchProject, SourcePolicy
from backend.app.storage.sqlite import SQLiteRepository, init_database


def _context(tmp_path: Path, llm_provider) -> KernelRuntimeContext:
    database_path = tmp_path / "specialists.sqlite3"
    init_database(database_path)
    project = ResearchProject(
        id="project-specialists",
        title="Knowledge Operations",
        domain="RAG",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
        source_policy=SourcePolicy.USER_MATERIALS_ONLY,
        status=ProjectStatus.DRAFT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return KernelRuntimeContext(
        project=project,
        repository=SQLiteRepository(database_path),
        state=SectorBreakerState.initialize(project_id=project.id, domain=project.domain, user_goal="maintain"),
        search_provider=None,
        llm_provider=llm_provider,
        emit_event=lambda event: asyncio.sleep(0),
    )


def test_specialist_task_rejects_unregistered_role() -> None:
    with pytest.raises(ValidationError):
        SpecialistTask(role="filesystem_admin", objective="overwrite vault")


def test_specialist_result_rejects_apply_or_cross_role_change() -> None:
    with pytest.raises(ValidationError):
        SpecialistResult(
            role=SpecialistRole.RESEARCHER,
            objective="research",
            summary="done",
            recommended_tool_calls=[{"tool_name": "apply_change_set"}],
        )
    with pytest.raises(ValidationError):
        SpecialistResult(
            role=SpecialistRole.VERIFIER,
            objective="verify",
            summary="done",
            proposed_change={"path": "RAG.md", "after_content": "# changed"},
        )


def test_delegate_specialists_fails_closed_on_disallowed_tool(tmp_path: Path) -> None:
    class UnsafeLLM:
        async def complete_structured(self, messages, response_schema):
            return response_schema.model_validate({
                "role": "researcher",
                "objective": "research",
                "summary": "I will apply it myself",
                "recommended_tool_calls": [{"tool_name": "apply_change_set"}],
            })

    observation = asyncio.run(delegate_specialists(
        ToolCall(
            tool_name="delegate_specialists",
            args={"tasks": [{"role": "researcher", "objective": "research"}]},
            reason="test boundary",
        ),
        _context(tmp_path, UnsafeLLM()),
    ))

    assert observation.success is False
    assert "ValidationError" in (observation.error or "")
