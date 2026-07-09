"""Regression tests for partial Agent Kernel success."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.models import (
    AgentActionType,
    AgentDecision,
    KernelObservation,
    KernelRunStatus,
    ToolCall,
    ToolSpec,
)
from backend.app.agent_kernel.runtime import AgentKernelRuntime
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry
from backend.app.agent_state.models import SectorBreakerState
from backend.app.schemas import Artifact, ArtifactType, MarketScope, ProjectMode, ResearchDepth, ResearchProject, SourcePolicy


def _project() -> ResearchProject:
    return ResearchProject(
        id="proj-001",
        title="T",
        domain="d",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
        source_policy=SourcePolicy.RELIABLE_FIRST,
        project_mode=ProjectMode.DOMAIN_KNOWLEDGE,
        status="draft",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class _Repo:
    def list_evidence(self, project_id):
        return []

    def list_documents(self, project_id):
        return []

    def list_artifacts(self, project_id):
        return []


def _make_real_artifact() -> Artifact:
    return Artifact(
        id="ART-KERNEL-L1-real001",
        project_id="proj-001",
        artifact_type=ArtifactType.DOMAIN_OVERVIEW,
        title="L1",
        content_path="docs/01-l1.md",
        content="# L1\n\n## S\n\n" + "x" * 800,
        schema_version="v2-agent-kernel",
        created_at=datetime.now(UTC),
    )


def test_card_failure_does_not_kill_run_with_real_artifacts() -> None:
    class Policy:
        def __init__(self):
            self.i = 0

        async def decide(self, **kwargs):
            self.i += 1
            if self.i == 1:
                return AgentDecision(
                    thought_summary="写卡片（会失败）",
                    action_type=AgentActionType.WRITE_ARTIFACT,
                    tool_call=ToolCall(tool_name="write_explainer_card", args={}, reason="缺参数"),
                )
            return AgentDecision(
                thought_summary="完成",
                action_type=AgentActionType.FINISH,
                stop_reason="done",
            )

    async def failing_card(tool_call, context):
        return KernelObservation(
            tool_name="write_explainer_card",
            success=False,
            summary="解释卡写作失败：缺少 title 或 focus。",
            error="missing title or focus",
        )

    registry = ToolRegistry()
    registry.register(ToolSpec(name="write_explainer_card", description="c"), failing_card)

    context = KernelRuntimeContext(
        project=_project(),
        repository=_Repo(),
        state=SectorBreakerState.initialize(project_id="proj-001", domain="d", user_goal="g"),
        search_provider=None,
        llm_provider=None,
        emit_event=lambda e: asyncio.sleep(0),
    )
    context.artifacts = [_make_real_artifact()]

    result = asyncio.run(AgentKernelRuntime(policy=Policy(), registry=registry).run(context))

    assert result.status == KernelRunStatus.COMPLETED
    assert "ART-KERNEL-L1-real001" in result.artifact_ids
    assert result.failed_writes
    assert result.partial_success is True
