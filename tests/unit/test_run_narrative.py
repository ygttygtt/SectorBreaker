"""Tests for the generate_run_narrative tool."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.narrative import generate_run_narrative
from backend.app.agent_state.models import SectorBreakerState
from backend.app.providers.fakes import FakeLLMProvider
from backend.app.schemas import Artifact, ArtifactType, MarketScope, ProjectMode, ResearchDepth, ResearchProject, SourcePolicy


def _project() -> ResearchProject:
    return ResearchProject(
        id="proj-001",
        title="T",
        domain="情趣用品",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
        source_policy=SourcePolicy.RELIABLE_FIRST,
        project_mode=ProjectMode.DOMAIN_KNOWLEDGE,
        status="draft",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _context(llm) -> KernelRuntimeContext:
    state = SectorBreakerState.initialize(project_id="proj-001", domain="情趣用品", user_goal="建库")
    state.evidence_refs = [f"EV-{i}" for i in range(99)]
    ctx = KernelRuntimeContext(
        project=_project(),
        repository=None,
        state=state,
        search_provider=None,
        llm_provider=llm,
        emit_event=lambda e: asyncio.sleep(0),
    )
    ctx.artifacts = [
        Artifact(
            id="ART-KERNEL-L1-a",
            project_id="proj-001",
            artifact_type=ArtifactType.DOMAIN_OVERVIEW,
            title="本源与边界",
            content_path="docs/01.md",
            content="x" * 800,
            schema_version="v2-agent-kernel",
            created_at=datetime.now(UTC),
        ),
    ]
    return ctx


def test_generate_run_narrative_creates_first_person_report() -> None:
    narrative_text = (
        "# 我是怎么调研情趣用品这个领域的\n\n"
        "## 起点\n\n我先搞清楚这个领域是什么。\n\n"
        "## 搜索与发现\n\n我一共搜索了 99 条资料，发现监管信息不足，于是又补搜了政策。\n\n"
        "## 我的判断\n\n我认为已经覆盖了核心层。" + "补充说明。" * 50
    )
    llm = FakeLLMProvider(response=narrative_text)
    ctx = _context(llm)
    tool_call = ToolCall(tool_name="generate_run_narrative", args={}, reason="收尾复盘")

    obs = asyncio.run(generate_run_narrative(tool_call, ctx))

    assert obs.success is True
    narrative_artifacts = [
        artifact for artifact in ctx.artifacts
        if artifact.artifact_type == ArtifactType.FOLLOW_UP_NOTE or "调研" in artifact.title
    ]
    assert narrative_artifacts
    assert obs.artifact_ids


def test_generate_run_narrative_without_llm_fails_gracefully() -> None:
    ctx = _context(llm=None)
    tool_call = ToolCall(tool_name="generate_run_narrative", args={}, reason="test")

    obs = asyncio.run(generate_run_narrative(tool_call, ctx))

    assert obs.success is False
