import asyncio
from datetime import UTC, datetime
from pathlib import Path

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.artifacts import write_vault_index
from backend.app.agent_kernel.tools.search import search_web
from backend.app.agent_kernel.tools.knowledge_base import propose_change_set
from backend.app.agent_state import SectorBreakerState
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    MarketScope,
    ProjectStatus,
    ResearchDepth,
    ResearchProject,
    SourcePolicy,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database


def _context(tmp_path: Path, *, source_policy: SourcePolicy, search_provider=None) -> KernelRuntimeContext:
    database_path = tmp_path / "permissions.sqlite3"
    init_database(database_path)
    project = ResearchProject(
        id="project-permissions",
        title="Permissions",
        domain="RAG",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
        source_policy=source_policy,
        status=ProjectStatus.DRAFT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return KernelRuntimeContext(
        project=project,
        repository=SQLiteRepository(database_path),
        state=SectorBreakerState.initialize(project_id=project.id, domain=project.domain, user_goal="maintain"),
        search_provider=search_provider,
        llm_provider=None,
        emit_event=lambda event: asyncio.sleep(0),
    )


def test_user_materials_only_policy_blocks_network_dispatch(tmp_path: Path) -> None:
    class SearchProviderMustNotRun:
        async def search(self, query):
            raise AssertionError("network provider must not be called")

    context = _context(
        tmp_path,
        source_policy=SourcePolicy.USER_MATERIALS_ONLY,
        search_provider=SearchProviderMustNotRun(),
    )
    observation = asyncio.run(search_web(
        ToolCall(
            tool_name="search_web",
            args={"query": "RAG", "search_goal": "test"},
            reason="test permission",
        ),
        context,
    ))

    assert observation.success is False
    assert observation.requires_human is True
    assert observation.error == "network search is not permitted"


def test_file_count_budget_blocks_generated_index(tmp_path: Path) -> None:
    context = _context(tmp_path, source_policy=SourcePolicy.OPEN_WEB)
    context.state.autonomy_policy.max_files_per_run = 1
    context.artifacts = [Artifact(
        id="ART-ONE",
        project_id=context.project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="Existing",
        content_path="Existing.md",
        content="# Existing",
        schema_version="v3-knowledge-ops",
    )]

    observation = asyncio.run(write_vault_index(
        ToolCall(
            tool_name="write_vault_index",
            args={"title": "Index", "index_goal": "connect notes"},
            reason="test budget",
        ),
        context,
    ))

    assert observation.success is False
    assert observation.requires_human is True
    assert observation.error == "max_files_per_run exhausted"
    assert len(context.artifacts) == 1


def test_apply_safe_auto_applies_allowed_create_but_not_existing_update(tmp_path: Path) -> None:
    context = _context(tmp_path, source_policy=SourcePolicy.OPEN_WEB)
    context.state.autonomy_policy.execution_mode = "apply_safe"
    create_observation = asyncio.run(propose_change_set(
        ToolCall(
            tool_name="propose_change_set",
            args={
                "summary": "create a safe card",
                "path": "cards/RAG.md",
                "after_content": "# RAG\n\nA managed knowledge card.",
                "factual_change": False,
            },
            reason="safe create",
        ),
        context,
    ))

    assert create_observation.success is True
    assert create_observation.requires_human is False
    assert create_observation.artifact_ids
    assert context.repository.list_change_sets(context.project.id)[0].status.value == "applied"

    existing = context.repository.list_artifacts(context.project.id)[0]
    update_observation = asyncio.run(propose_change_set(
        ToolCall(
            tool_name="propose_change_set",
            args={
                "summary": "update existing card",
                "path": existing.content_path,
                "after_content": "# RAG\n\nUpdated content.",
                "factual_change": False,
            },
            reason="existing update must remain reviewed",
        ),
        context,
    ))

    assert update_observation.success is True
    assert update_observation.requires_human is True
    assert context.repository.list_artifacts(context.project.id)[0].id == existing.id
