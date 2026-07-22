import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.reducer import apply_state_delta
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.artifacts import write_explainer_card, write_layer_document, write_vault_index
from backend.app.agent_kernel.tools.search import search_web
from backend.app.agent_kernel.tools.state import evaluate_coverage, internalize_observation, manage_state_memory, reflect_on_progress
from backend.app.agent_state import KnowledgeClaim, SectorBreakerState, SourceMemory
from backend.app.providers.interfaces import SearchResult
from backend.app.providers.fakes import FakeContentExtractionProvider
from backend.app.providers.source_verification import HeuristicSourceVerificationProvider
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
    assert llm.calls == 4
    assert observation.data["attempts"] == 4
    assert "LLM 分节写作失败" in observation.summary


def test_search_web_supports_human_query_variants() -> None:
    class FakeSearchProvider:
        def __init__(self) -> None:
            self.queries = []

        async def search(self, query):
            self.queries.append((query.query, query.max_results, query.allowed_domains))
            return [
                SearchResult(
                    title=f"{query.query} result",
                    url=f"https://github.com/example/{len(self.queries)}",
                    snippet=f"{query.query} snippet",
                )
            ]

    class FakeRepository:
        def __init__(self) -> None:
            self.evidence = []

        def list_evidence(self, project_id):
            return self.evidence

        def add_evidence(self, evidence):
            self.evidence.append(evidence)

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

    async def emit(event):
        return None

    search_provider = FakeSearchProvider()
    repository = FakeRepository()
    context = KernelRuntimeContext(
        project=_project(),
        repository=repository,  # type: ignore[arg-type]
        state=SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库"),
        search_provider=search_provider,  # type: ignore[arg-type]
        llm_provider=None,
        emit_event=emit,
    )

    observation = asyncio.run(search_web(
        ToolCall(
            tool_name="search_web",
            args={
                "query": "API 中转站 原理",
                "queries": ["API 中转站 原理", "API 中转站 One API New API", "AI API relay protocol conversion"],
                "layer_hint": "L3_how",
                "search_goal": "找到实现机制和常见工具。",
                "preferred_domains": ["github.com", "arxiv.org"],
                "max_results": 9,
            },
            reason="用真人式 query variants 覆盖同一缺口。",
        ),
        context,
    ))

    assert observation.success is True
    assert [item[0] for item in search_provider.queries] == [
        "API 中转站 原理",
        "API 中转站 One API New API",
        "AI API relay protocol conversion",
    ]
    assert all(limit == 3 for _, limit, _ in search_provider.queries)
    assert all(domains == ["github.com", "arxiv.org"] for _, _, domains in search_provider.queries)
    assert observation.data["queries"] == [item[0] for item in search_provider.queries]
    assert len(observation.state_delta.source_memories) == 3
    assert len(repository.evidence) == 3


def test_search_web_extracts_page_body_and_persists_honest_assessment() -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.evidence = []

        def list_evidence(self, project_id):
            return self.evidence

        def add_evidence(self, evidence):
            self.evidence.append(evidence)

    async def emit(event):
        return None

    url = "https://www.stats.gov.cn/report"
    body = "国家统计局公开报告正文。" * 30
    repository = FakeRepository()
    context = KernelRuntimeContext(
        project=_project(),
        repository=repository,  # type: ignore[arg-type]
        state=SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库"),
        search_provider=type("Provider", (), {
            "search": lambda self, query: _async_value([
                SearchResult(title="国家统计报告", url=url, snippet="搜索摘要不能替代正文。")
            ])
        })(),  # type: ignore[arg-type]
        content_extraction_provider=FakeContentExtractionProvider({
            url: {
                "title": "国家统计报告正文",
                "raw_text": body,
                "domain": "stats.gov.cn",
                "extraction_provider": "fake_content",
            }
        }),
        source_verification_provider=HeuristicSourceVerificationProvider(),
        llm_provider=None,
        emit_event=emit,
    )

    observation = asyncio.run(search_web(
        ToolCall(
            tool_name="search_web",
            args={"query": "国家统计", "search_goal": "读取官方报告", "max_results": 1},
            reason="测试生产搜索工具消费正文。",
        ),
        context,
    ))

    assert observation.success is True
    assert len(repository.evidence) == 1
    evidence = repository.evidence[0]
    assert evidence.raw_excerpt == body
    assert evidence.extraction_provider == "fake_content"
    assert evidence.extracted_at is not None
    assert evidence.source_quality.value == "high"
    assert evidence.verification_status.value == "partially_verified"
    assert observation.data["extraction_diagnostics"][0]["success"] is True


async def _async_value(value):
    return value


def test_write_layer_document_falls_back_to_sections_after_full_document_errors() -> None:
    class FlakyThenSectionLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, messages):
            self.calls += 1
            if self.calls <= 2:
                raise ConnectionError("temporary upstream disconnect")
            return (
                "## 分节内容\n\n"
                "这是一段足够长的分节内容，用来验证当完整文档写作因为上游连接失败时，writer 会继续尝试更小的分节写作，而不是直接失败。"
                "内容包含 API 中转站的定义、证据状态、待验证问题和 Obsidian 可读结构。"
                "EV-KERNEL-1 用于证明证据引用能够继续保留。"
                "这一节还会解释为什么分节写作更适合不稳定的中转接口：它降低单次请求长度，让模型只处理一个小目标，"
                "即使上游偶发断连，也能在下一节继续恢复，而不是把整篇文档直接判定失败。"
            )

        async def complete_structured(self, messages, response_schema):
            raise AssertionError("Markdown writing must not use structured completion")

    class FakeRepository:
        def list_evidence(self, project_id):
            return []

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

        def get_evidence(self, evidence_id):
            raise KeyError(evidence_id)

    async def emit(event):
        return None

    state = SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库")
    state.evidence_refs.append("EV-KERNEL-1")
    context = KernelRuntimeContext(
        project=_project(),
        repository=FakeRepository(),  # type: ignore[arg-type]
        state=state,
        search_provider=None,
        llm_provider=FlakyThenSectionLLM(),  # type: ignore[arg-type]
        emit_event=emit,
    )

    observation = asyncio.run(write_layer_document(
        ToolCall(
            tool_name="write_layer_document",
            args={"layer_id": "L1_what_why", "title": "L1 本源与需求", "writing_goal": "解释是什么"},
            reason="测试完整写作失败后分节成功。",
        ),
        context,
    ))

    assert observation.success is True
    assert len(context.artifacts) == 1
    assert context.artifacts[0].schema_version == "v3-knowledge-ops"
    assert "## 分节内容" in context.artifacts[0].content
    assert observation.state_delta.artifact_ids == [context.artifacts[0].id]


def test_write_explainer_card_creates_observable_knowledge_card() -> None:
    class CardLLM:
        async def complete(self, messages):
            return (
                "# 反向代理\n\n"
                "## 一句话解释\n\n"
                "反向代理是位于客户端和上游服务之间的代理层。在 API 中转站里，它常被用来统一入口、隐藏上游差异，并把请求转交给真正的模型服务。"
                "这只是基于当前 State 的 partial 解释，仍需结合 EV-KERNEL-1 等证据继续验证。\n\n"
                "## 为什么它重要\n\n"
                "如果没有反向代理，用户通常需要直接面对不同厂商的鉴权、域名、网络连通性和计费差异。中转站把这些差异包装成一个较稳定的调用面，"
                "让开发者先理解 [[协议转换]]、[[模型路由]] 和 [[上游供应]] 的关系。\n\n"
                "## 它如何运作\n\n"
                "典型链路是客户端请求先进入代理层，代理层检查 Key、额度和模型名，再把请求转发给上游模型 API。返回结果再被整理成用户期望的格式。"
                "这里涉及请求头、路径、模型名和响应结构的适配。\n\n"
                "## 和本领域的关系\n\n"
                "API 中转站的价值不只在代理请求，还在统一多模型访问、做配额控制、降低接入摩擦。因此它应当和 [[API 中转站]] 主文档互相链接。\n\n"
                "## 证据与待验证\n\n"
                "- 当前证据来自 EV-KERNEL-1，可信度仍是 partial。\n"
                "- 下一轮需要验证不同开源网关项目如何实现反向代理和协议适配。"
            )

        async def complete_structured(self, messages, response_schema):
            raise AssertionError("Explainer card writing must use plain text completion")

    class FakeRepository:
        def list_evidence(self, project_id):
            return []

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

        def get_evidence(self, evidence_id):
            raise KeyError(evidence_id)

    async def emit(event):
        return None

    state = SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库")
    state.evidence_refs.append("EV-KERNEL-1")
    context = KernelRuntimeContext(
        project=_project(),
        repository=FakeRepository(),  # type: ignore[arg-type]
        state=state,
        search_provider=None,
        llm_provider=CardLLM(),  # type: ignore[arg-type]
        emit_event=emit,
    )

    observation = asyncio.run(write_explainer_card(
        ToolCall(
            tool_name="write_explainer_card",
            args={
                "card_kind": "concept",
                "title": "反向代理",
                "focus": "解释反向代理为什么是 API 中转站的基础概念",
                "layer_id": "L3_how",
                "writing_goal": "给新手一张可链接的概念卡。",
            },
            reason="主文档发现术语盲区。",
        ),
        context,
    ))

    assert observation.success is True
    assert len(context.artifacts) == 1
    artifact = context.artifacts[0]
    assert artifact.schema_version == "v3-knowledge-ops"
    assert artifact.content_path == "concepts/反向代理.md"
    assert artifact.source_evidence_ids == ["EV-KERNEL-1"]
    assert observation.state_delta.artifact_ids == [artifact.id]
    assert "[[协议转换]]" in artifact.content


def test_write_vault_index_links_main_docs_and_cards() -> None:
    class FakeRepository:
        def list_evidence(self, project_id):
            return []

        def list_documents(self, project_id):
            return []

        def list_artifacts(self, project_id):
            return []

    async def emit(event):
        return None

    context = KernelRuntimeContext(
        project=_project(),
        repository=FakeRepository(),  # type: ignore[arg-type]
        state=SectorBreakerState.initialize(project_id="project-kernel", domain="API中转站", user_goal="建库"),
        search_provider=None,
        llm_provider=None,
        emit_event=emit,
    )
    from backend.app.schemas import Artifact, ArtifactType

    context.artifacts.extend([
        Artifact(
            id="ART-1",
            project_id="project-kernel",
            artifact_type=ArtifactType.DOMAIN_OVERVIEW,
            title="API 中转站：本源与需求",
            content_path="01-API中转站-本源与需求.md",
            content="# API 中转站：本源与需求\n\n## 小节\n\n正文",
            schema_version="v2-agent-kernel",
            created_at=datetime.now(UTC),
        ),
        Artifact(
            id="ART-CARD-1",
            project_id="project-kernel",
            artifact_type=ArtifactType.CORE_CONCEPTS,
            title="反向代理",
            content_path="concepts/反向代理.md",
            content="# 反向代理\n\n## 小节\n\n正文",
            schema_version="v2-agent-kernel-card",
            created_at=datetime.now(UTC),
        ),
    ])

    observation = asyncio.run(write_vault_index(
        ToolCall(
            tool_name="write_vault_index",
            args={"title": "API 中转站知识库导航", "index_goal": "给录屏演示一个总入口。"},
            reason="主文档和解释卡都已有，需要总入口。",
        ),
        context,
    ))

    assert observation.success is True
    index_artifact = context.artifacts[-1]
    assert index_artifact.schema_version == "v3-knowledge-ops"
    assert index_artifact.content_path == "00-知识库导航.md"
    assert "[[01-API中转站-本源与需求]]" in index_artifact.content
    assert "[[反向代理]]" in index_artifact.content


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
