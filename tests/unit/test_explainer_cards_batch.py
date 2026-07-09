"""Tests for batch explainer card writing."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.artifacts import write_explainer_cards_batch
from backend.app.agent_state.models import SectorBreakerState
from backend.app.schemas import MarketScope, ProjectMode, ProjectStatus, ResearchDepth, ResearchProject, SourcePolicy


def _project() -> ResearchProject:
    return ResearchProject(
        id="project-kernel",
        title="API中转站",
        domain="API中转站",
        market_scope=MarketScope.MIXED,
        source_policy=SourcePolicy.OPEN_WEB,
        depth=ResearchDepth.QUICK,
        project_mode=ProjectMode.DOMAIN_KNOWLEDGE,
        status=ProjectStatus.DRAFT,
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

    def get_evidence(self, evidence_id):
        raise KeyError(evidence_id)


class _CardLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages):
        self.calls += 1
        title = f"批量解释卡 {self.calls}"
        return (
            f"# {title}\n\n"
            "## 一句话解释\n\n"
            "这是面向新手的解释卡，用来把主文档里容易卡住的概念拆开说明。"
            "它会明确指出当前内容只是 partial 版本，并等待更多 EV-KERNEL-1 证据补强。"
            "为了满足知识库可读性，这里补充足够的背景、边界和读者使用方式。\n\n"
            "## 为什么它重要\n\n"
            "如果读者不了解这个概念，就很难理解 [[API 中转站]]、[[模型路由]] 和 [[上游供应]] 之间的关系。"
            "解释卡把术语从主文档中拆出来，避免主线文档变成术语堆叠。"
            "它也能在后续补库时独立更新，而不必反复改写主文档。\n\n"
            "## 它如何运作\n\n"
            "卡片会先给出定义，再解释机制、参与方和常见误解。"
            "随后把它连接回主文档，让读者知道这个概念在哪些章节会被用到。"
            "如果证据不足，卡片会保留待验证问题，而不是把推测写成事实。\n\n"
            "## 和主文档的关系\n\n"
            "这张卡应该链接到 [[协议转换]]、[[反向代理]] 和 [[调用链路]]。"
            "它帮助主文档保持结构清楚，同时让知识库可以继续横向生长。\n\n"
            "## 证据与待验证\n\n"
            "- 当前引用 EV-KERNEL-1，可信度为 partial。\n"
            "- 下一轮需要补充真实项目文档、厂商说明和用户案例。"
        )


def test_write_explainer_cards_batch_creates_multiple_cards() -> None:
    state = SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库")
    state.evidence_refs.append("EV-KERNEL-1")
    context = KernelRuntimeContext(
        project=_project(),
        repository=_Repo(),  # type: ignore[arg-type]
        state=state,
        search_provider=None,
        llm_provider=_CardLLM(),  # type: ignore[arg-type]
        emit_event=lambda event: asyncio.sleep(0),
    )

    observation = asyncio.run(write_explainer_cards_batch(
        ToolCall(
            tool_name="write_explainer_cards_batch",
            args={
                "cards": [
                    {
                        "card_kind": "concept",
                        "title": "反向代理",
                        "focus": "解释反向代理为什么是 API 中转站基础概念",
                        "writing_goal": "给新手一张概念卡。",
                    },
                    {
                        "card_kind": "process",
                        "title": "模型路由",
                        "focus": "解释模型路由怎样影响调用体验",
                        "writing_goal": "补充主文档中的流程理解。",
                    },
                ],
            },
            reason="主文档已完成，补充互不依赖的卡片。",
        ),
        context,
    ))

    assert observation.success is True
    assert len(observation.artifact_ids) == 2
    assert len(context.artifacts) == 2
    assert {artifact.schema_version for artifact in context.artifacts} == {"v2-agent-kernel-card"}
    assert observation.state_delta.artifact_ids == observation.artifact_ids
