"""Tests for revise_layer_document tool."""
from __future__ import annotations

import asyncio
from pathlib import Path

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.artifacts import revise_layer_document
from backend.app.agent_state.models import SectorBreakerState
from backend.app.providers.fakes import FakeLLMProvider
from backend.app.schemas import Artifact, ArtifactType, ResearchProject
from backend.app.storage.sqlite import SQLiteRepository, init_database
from datetime import UTC, datetime


def _make_repo(tmp_path: Path) -> SQLiteRepository:
    db = tmp_path / "test.db"
    init_database(db)
    return SQLiteRepository(db)


def _make_project() -> ResearchProject:
    from backend.app.schemas import MarketScope, ResearchDepth, SourcePolicy, ProjectMode
    return ResearchProject(
        id="proj-001",
        title="Test Project",
        domain="test-domain",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.STANDARD,
        source_policy=SourcePolicy.RELIABLE_FIRST,
        project_mode=ProjectMode.DOMAIN_KNOWLEDGE,
        status="draft",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_old_artifact() -> Artifact:
    return Artifact(
        id="ART-KERNEL-L1-old001",
        project_id="proj-001",
        artifact_type=ArtifactType.DOMAIN_OVERVIEW,
        title="What and Why",
        content_path="01-what-why.md",
        content="# What and Why\n\n## Intro\n\nShort original content.",
        schema_version="v2-agent-kernel",
        created_at=datetime.now(UTC),
    )


def _make_context(repo: SQLiteRepository, llm=None) -> KernelRuntimeContext:
    state = SectorBreakerState.initialize(
        project_id="proj-001",
        domain="test-domain",
        user_goal="build knowledge base",
    )
    state.evidence_refs = ["EV-KERNEL-001"]
    return KernelRuntimeContext(
        project=_make_project(),
        repository=repo,
        state=state,
        search_provider=None,
        llm_provider=llm,
        emit_event=lambda e: asyncio.sleep(0),
    )


def test_revise_layer_document_creates_new_supersedes_old(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    old_artifact = _make_old_artifact()
    revised_content = (
        "# What and Why (Revised)\n\n"
        "## Section One: Definition\n\nExpanded content with more detail about the domain. "
        "This section provides a thorough explanation of what the domain is and why it exists. "
        "We cover the fundamental concepts and the historical context that led to its creation.\n\n"
        "## Section Two: Problem Space\n\nAdditional context here.[^EV-KERNEL-001] "
        "The domain addresses several critical pain points that users face in their daily workflows. "
        "Understanding these pain points helps us appreciate why the domain has grown so rapidly.\n\n"
        "## Section Three: Core Boundaries\n\nMore analysis of what falls inside and outside the domain. "
        "A clear boundary definition helps practitioners avoid scope creep and maintain focus on the core value proposition.\n\n"
        "## Section Four: Key Takeaways\n\nConclusion with actionable insights for practitioners. "
        "The domain's success depends on understanding these boundaries and leveraging the right tools and methodologies."
    )
    llm = FakeLLMProvider(response=revised_content)
    context = _make_context(repo, llm)
    context.artifacts = [old_artifact]

    tool_call = ToolCall(
        tool_name="revise_layer_document",
        args={
            "artifact_id": "ART-KERNEL-L1-old001",
            "layer_id": "L1_what_why",
            "revision_goal": "Add more detail and evidence citations",
        },
        reason="Original too short",
    )
    observation = asyncio.run(revise_layer_document(tool_call, context))

    assert observation.success is True
    assert len(context.artifacts) == 2
    new_art = next(a for a in context.artifacts if a.id != "ART-KERNEL-L1-old001")
    old_art = next(a for a in context.artifacts if a.id == "ART-KERNEL-L1-old001")
    assert new_art.id.startswith("ART-KERNEL-REV-")
    assert old_art.superseded_by == new_art.id
    assert "Revised" in new_art.content


def test_revise_layer_document_fails_without_llm(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    old_artifact = _make_old_artifact()
    context = _make_context(repo, llm=None)
    context.artifacts = [old_artifact]

    tool_call = ToolCall(
        tool_name="revise_layer_document",
        args={"artifact_id": "ART-KERNEL-L1-old001", "revision_goal": "Expand content"},
        reason="test",
    )
    observation = asyncio.run(revise_layer_document(tool_call, context))
    assert observation.success is False
    assert "LLM" in observation.summary


def test_revise_layer_document_fails_for_missing_artifact(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    context = _make_context(repo, llm=FakeLLMProvider(response="test"))
    context.artifacts = []

    tool_call = ToolCall(
        tool_name="revise_layer_document",
        args={"artifact_id": "NONEXISTENT-ID", "revision_goal": "test"},
        reason="test",
    )
    observation = asyncio.run(revise_layer_document(tool_call, context))
    assert observation.success is False
    assert "artifact" in observation.error.lower()
