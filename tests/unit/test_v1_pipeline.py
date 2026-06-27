import asyncio
from datetime import UTC, datetime

from backend.app.providers.interfaces import SearchQuery, SearchResult
from backend.app.schemas import (
    MarketScope,
    ProjectStatus,
    ResearchProject,
    ResearchDepth,
    SourcePolicy,
)
from backend.app.v1_pipeline import (
    DomainArchitecture,
    DomainConcept,
    DomainKnowledgeBase,
    DomainTool,
    V1KnowledgeContent,
    _build_knowledge_content,
    _build_knowledge_database,
    _render_domain_overview,
    _render_learning_path,
    _evidence_brief,
    _evidence_lines,
    _fallback_database,
    _is_v1_result_topic_relevant,
    _search_result_to_evidence,
    run_v1_knowledge_pipeline,
)


def _project() -> ResearchProject:
    return ResearchProject(
        id="project-v1-clean",
        title="Agent开发",
        domain="Agent开发",
        market_scope=MarketScope.MIXED,
        source_policy=SourcePolicy.RELIABLE_FIRST,
        depth=ResearchDepth.QUICK,
        status=ProjectStatus.DRAFT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_v1_search_evidence_cleans_github_navigation_noise() -> None:
    noisy_snippet = (
        "[Skip to content](https://github.com/org/repo#start-of-content). "
        "[Sign in](https://github.com/login?return_to=https%3A%2F%2Fgithub.com%2Forg%2Frepo). "
        "* [GitHub Skills](https://skills.github.com/). "
        "Navigation Menu. Search code, repositories, users, issues, pull requests. "
        "| [README](https://github.com/org/repo#readme) | [Issues](https://github.com/org/repo/issues) | "
        "Agent development frameworks compare LangGraph, CrewAI, OpenAI Agents SDK, evaluation, "
        "tool calling, memory, orchestration, deployment, and production safety patterns. "
        "This practical repository is useful as a lead but needs verification."
    )

    evidence = _search_result_to_evidence(
        _project(),
        SearchResult(
            title="Example Agent Frameworks - GitHub",
            url="https://github.com/org/repo",
            snippet=noisy_snippet,
        ),
        1,
    )

    assert "Skip to content" not in evidence.snippet
    assert "Sign in" not in evidence.snippet
    assert "https://github.com/login" not in evidence.snippet
    assert "Agent development frameworks" in evidence.snippet
    assert len(evidence.snippet) <= 420
    assert evidence.summary == evidence.snippet
    assert evidence.claims[0].text == evidence.snippet


def test_v1_evidence_brief_and_lines_use_readable_capped_text() -> None:
    evidence = _search_result_to_evidence(
        _project(),
        SearchResult(
            title="Long Agent Market Source",
            url="https://example.com/agent-market",
            snippet="Agent market signal. " * 80,
        ),
        1,
    )

    brief = _evidence_brief([evidence])
    lines = _evidence_lines([evidence])

    assert len(brief) < 650
    assert len(lines) < 650
    assert "Agent market signal." in brief
    assert "Agent market signal." in lines


def test_v1_reliable_first_falls_back_to_open_web_when_reliable_search_is_empty() -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.evidence = []
            self.artifacts = []

        def list_evidence(self, project_id: str):
            return []

        def add_evidence(self, item):
            self.evidence.append(item)

        def add_artifact(self, artifact):
            self.artifacts.append(artifact)

    class EmptyThenOpenWebSearch:
        def __init__(self) -> None:
            self.queries: list[SearchQuery] = []

        async def search(self, query: SearchQuery) -> list[SearchResult]:
            self.queries.append(query)
            if query.allowed_domains:
                return []
            return [
                SearchResult(
                    title="AI Agent framework trends 2026",
                    url="https://example.com/agent-framework-trends",
                    snippet="AI Agent development is moving toward production orchestration, evaluation, and framework selection.",
                )
            ]

    repository = FakeRepository()
    search_provider = EmptyThenOpenWebSearch()

    asyncio.run(
        run_v1_knowledge_pipeline(
            project=_project(),
            repository=repository,  # type: ignore[arg-type]
            search_provider=search_provider,
            llm_provider=None,
        )
    )

    assert len(search_provider.queries) >= 2
    assert search_provider.queries[0].allowed_domains
    assert search_provider.queries[1].allowed_domains == []
    assert len(repository.evidence) == 1
    assert repository.evidence[0].source_title == "AI Agent framework trends 2026"


def test_v1_pipeline_runs_supplemental_search_when_evidence_is_insufficient() -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.evidence = []
            self.artifacts = []

        def list_evidence(self, project_id: str):
            return []

        def add_evidence(self, item):
            self.evidence.append(item)

        def add_artifact(self, artifact):
            self.artifacts.append(artifact)

    class SparseThenSupplementalSearch:
        def __init__(self) -> None:
            self.queries: list[SearchQuery] = []

        async def search(self, query: SearchQuery) -> list[SearchResult]:
            self.queries.append(query)
            if len(self.queries) == 1:
                return [
                    SearchResult(
                        title="AI Agent information gathering overview",
                        url="https://example.com/agent-overview",
                        snippet="AI Agent information gathering uses tools, workflow orchestration, search APIs, evaluation, and source verification.",
                    )
                ]
            return [
                SearchResult(
                    title=f"AI Agent source verification practice {index}",
                    url=f"https://example.com/agent-source-{index}",
                    snippet="AI Agent information gathering needs cross-source verification, official documents, implementation cases, and evaluation.",
                )
                for index in range(2, 10)
            ]

    repository = FakeRepository()
    search_provider = SparseThenSupplementalSearch()
    events = []

    async def emit(event):
        events.append(event)

    asyncio.run(
        run_v1_knowledge_pipeline(
            project=_project().model_copy(update={"source_policy": SourcePolicy.OPEN_WEB}),
            repository=repository,  # type: ignore[arg-type]
            search_provider=search_provider,
            llm_provider=None,
            emit=emit,
        )
    )

    assert len(search_provider.queries) == 2
    assert "权威资料" in search_provider.queries[1].query
    assert len(repository.evidence) >= 8
    assert any("补充一轮开放搜索" in event.message for event in events)
    assert any("资料基本可用" in event.message or "资料充足度检查通过" in event.message for event in events)


def test_v1_pipeline_filters_developer_repository_and_attachment_noise() -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.evidence = []
            self.artifacts = []

        def list_evidence(self, project_id: str):
            return []

        def add_evidence(self, item):
            self.evidence.append(item)

        def add_artifact(self, artifact):
            self.artifacts.append(artifact)

    class NoisySearch:
        async def search(self, query: SearchQuery) -> list[SearchResult]:
            return [
                SearchResult(
                    title="GitHub - org/awesome-agent-list",
                    url="https://github.com/org/awesome-agent-list",
                    snippet="Navigation Menu. Search code, repositories, users, issues, pull requests. Agent list.",
                ),
                SearchResult(
                    title="[PDF] unrelated attachment",
                    url="https://example.com/report.pdf",
                    snippet="PDF table of contents.",
                ),
                SearchResult(
                    title="AI Agent enterprise adoption trends 2026",
                    url="https://example.com/ai-agent-trends-2026",
                    snippet="AI Agent development is shifting from demos to production workflows, evaluation, orchestration, and governance.",
                ),
            ]

    repository = FakeRepository()

    asyncio.run(
        run_v1_knowledge_pipeline(
            project=_project(),
            repository=repository,  # type: ignore[arg-type]
            search_provider=NoisySearch(),
            llm_provider=None,
        )
    )

    assert [item.source_title for item in repository.evidence] == ["AI Agent enterprise adoption trends 2026"]


def test_v1_knowledge_content_accepts_object_sections_from_llm() -> None:
    class ObjectSectionLLM:
        async def complete_structured(self, messages, response_schema):
            return response_schema.model_validate({
                "sections": [
                    {"title": "工程化趋势", "content": "AI Agent 开发开始关注评测、部署和治理。"},
                ],
            })

    content = asyncio.run(
        _build_knowledge_content(
            project=_project(),
            evidence=[],
            llm_provider=ObjectSectionLLM(),
        )
    )

    assert isinstance(content, V1KnowledgeContent)
    assert "工程化趋势" in content.core_concepts


def test_v1_knowledge_content_falls_back_when_llm_schema_is_invalid() -> None:
    class BrokenLLM:
        async def complete_structured(self, messages, response_schema):
            raise ValueError("provider returned invalid structured output")

    content = asyncio.run(
        _build_knowledge_content(
            project=_project(),
            evidence=[],
            llm_provider=BrokenLLM(),
        )
    )

    assert "Agent开发" in content.domain_overview


def test_v1_builds_structured_domain_knowledge_base_from_evidence() -> None:
    evidence = [
        _search_result_to_evidence(
            _project(),
            SearchResult(
                title="ADK Arena: Evaluating Agent Development Kits via LLM-as-a-Developer",
                url="https://arxiv.org/html/2606.05548v1",
                snippet=(
                    "ADK Arena evaluates LangGraph, CrewAI, OpenAI Agents SDK, AutoGen, "
                    "and other AI Agent development kits through a validate-and-feedback loop."
                ),
            ),
            1,
        ),
        _search_result_to_evidence(
            _project(),
            SearchResult(
                title="Agentic Artificial Intelligence architectures and evaluation",
                url="https://arxiv.org/html/2601.12560v1",
                snippet=(
                    "Agentic AI systems perceive, reason, plan, use tools, maintain memory, "
                    "and act through planner-executor, workflow, multi-agent, and RAG-agent architectures."
                ),
            ),
            2,
        ),
    ]

    database = asyncio.run(
        _build_knowledge_database(
            project=_project(),
            evidence=evidence,
            llm_provider=None,
        )
    )

    assert isinstance(database, DomainKnowledgeBase)
    assert len(database.concepts) >= 3
    assert len(database.architectures) >= 2
    assert len(database.tools) >= 2
    assert len(database.learning_path) >= 4
    assert any("工具调用" in concept.name or "Tool" in concept.name for concept in database.concepts)
    assert any("LangGraph" in tool.name for tool in database.tools)


def test_v1_chinese_topic_relevance_does_not_require_exact_full_phrase() -> None:
    assert _is_v1_result_topic_relevant(
        "大模型开发就业",
        "2026 最火 AI 岗位！大模型驱动下的 5 大就业方向",
        "大模型应用开发岗位需要 RAG 开发、Agent 架构设计、模型 API 调用、Python 工程能力和业务理解。",
    )


def test_v1_large_model_career_fallback_is_topic_specific() -> None:
    database = _fallback_database(_project().model_copy(update={
        "title": "大模型开发就业",
        "domain": "大模型开发就业",
    }), [])

    assert any("大模型" in concept.name for concept in database.concepts)
    assert any("RAG" in architecture.name or "Agent" in architecture.name for architecture in database.architectures)
    assert any("Python" in tool.name or "LangChain" in tool.name for tool in database.tools)
    assert all("LangGraph" not in concept.name for concept in database.concepts[:1])


def test_v1_pipeline_uses_llm_to_write_each_export_artifact_and_emits_progress() -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.evidence = []
            self.artifacts = []

        def list_evidence(self, project_id: str):
            return []

        def add_evidence(self, item):
            self.evidence.append(item)

        def add_artifact(self, artifact):
            self.artifacts.append(artifact)

    class UsefulSearch:
        async def search(self, query: SearchQuery) -> list[SearchResult]:
            return [
                SearchResult(
                    title="大模型应用开发岗位技能要求",
                    url="https://example.com/llm-job",
                    snippet="大模型应用开发岗位要求 Python、RAG、Agent、模型 API、后端工程化和业务理解。",
                )
            ]

    class WritingLLM:
        def __init__(self) -> None:
            self.string_calls = 0

        async def complete_structured(self, messages, response_schema):
            if response_schema is DomainKnowledgeBase:
                return response_schema.model_validate({
                    "overview": "大模型开发就业需要理解应用开发、RAG、Agent、工程化和作品集。",
                    "concepts": [
                        {"name": "大模型应用开发", "definition": "调用和集成大模型能力。", "why_it_matters": "岗位核心。", "related": ["RAG"], "evidence_ids": ["EV-V1-project-v1-clean-1"]},
                        {"name": "RAG", "definition": "检索增强生成。", "why_it_matters": "企业知识库常用。", "related": ["向量数据库"], "evidence_ids": ["EV-V1-project-v1-clean-1"]},
                        {"name": "Agent", "definition": "会规划和调用工具的系统。", "why_it_matters": "应用层进阶能力。", "related": ["工具调用"], "evidence_ids": ["EV-V1-project-v1-clean-1"]},
                    ],
                    "architectures": [
                        {"name": "RAG 应用架构", "summary": "检索后生成。", "use_cases": ["知识库"], "strengths": ["常见"], "limitations": ["依赖数据"], "evidence_ids": ["EV-V1-project-v1-clean-1"]},
                        {"name": "Agent 工作流架构", "summary": "规划并调用工具。", "use_cases": ["自动化"], "strengths": ["进阶"], "limitations": ["调试难"], "evidence_ids": ["EV-V1-project-v1-clean-1"]},
                    ],
                    "tools": [
                        {"name": "Python", "category": "language", "use_case": "开发后端和脚本。", "tradeoffs": "需要工程化。", "evidence_ids": ["EV-V1-project-v1-clean-1"]},
                        {"name": "LangChain / LangGraph", "category": "framework", "use_case": "RAG 和 Agent。", "tradeoffs": "抽象多。", "evidence_ids": ["EV-V1-project-v1-clean-1"]},
                    ],
                    "trends": ["应用开发岗位重视 RAG、Agent 和工程化。"],
                    "learning_path": ["学 API", "学 RAG", "学 Agent", "做项目"],
                    "open_questions": ["岗位 JD 高频技能是什么？"],
                })
            if response_schema is str:
                self.string_calls += 1
                return (
                    "# LLM 写作产物\n\n"
                    "## 背景\n\n大模型开发就业不是简单学习一个框架，而是理解岗位如何要求模型 API、"
                    "RAG、Agent、后端工程化、业务理解和作品集表达。\n\n"
                    "## 结构化说明\n\n这份文档会把概念、架构、工具、学习路径和证据组织成可继续维护的知识卡片。"
                    "它不是搜索摘要堆叠，而是基于证据重新组织后的学习资料。\n\n"
                    "## 学习建议\n\n学习者应该先确认岗位方向，再选择项目。应用开发岗通常需要能把模型 API 接入后端，"
                    "能实现 RAG 检索，能解释 Agent 工具调用流程，并能把日志、异常、权限和成本控制写进项目。"
                    "如果只会调用一个聊天接口，输出就很难区别于普通网页问答；如果能展示完整工程链路，"
                    "就能更像一个真实岗位候选人。证据：EV-V1-project-v1-clean-1。\n\n"
                    "## 作品集\n\n作品集至少应包含一个知识库问答项目、一个工具调用或 Agent 工作流项目、"
                    "一个部署后的演示入口，以及一份说明文档。说明文档要讲清楚问题、架构、数据流、失败处理、"
                    "评测方式和下一步改进，而不是只贴截图。证据：EV-V1-project-v1-clean-1。\n\n"
                    "## 证据\n\n- EV-V1-project-v1-clean-1\n\n"
                    "## 下一步\n\n继续补充岗位原始 JD、官方文档和项目案例，用来验证学习路线是否符合真实招聘要求。\n"
                )
            raise AssertionError(f"unexpected schema: {response_schema}")

    repository = FakeRepository()
    llm = WritingLLM()
    events = []

    async def emit(event):
        events.append(event)

    asyncio.run(
        run_v1_knowledge_pipeline(
            project=_project().model_copy(update={"domain": "大模型开发就业", "title": "大模型开发就业"}),
            repository=repository,  # type: ignore[arg-type]
            search_provider=UsefulSearch(),
            llm_provider=llm,
            emit=emit,
        )
    )

    assert llm.string_calls == 7
    assert len(repository.artifacts) == 7
    assert all("LLM 写作产物" in artifact.content for artifact in repository.artifacts)
    assert any(event.gate == "document_writing" and "正在写作" in event.message for event in events)


def test_v1_renders_useful_markdown_from_domain_database() -> None:
    database = DomainKnowledgeBase(
        overview="AI Agent 开发知识库用于理解概念、架构、工具链和学习路径。",
        concepts=[
            DomainConcept(
                name="工具调用",
                definition="Agent 通过标准接口调用外部工具完成模型本身不能直接完成的动作。",
                why_it_matters="它决定 Agent 能否从聊天走向真实任务执行。",
                related=["MCP", "函数调用"],
                evidence_ids=["EV-1"],
            ),
            DomainConcept(
                name="记忆",
                definition="保存短期上下文和长期知识，使 Agent 能跨步骤保持状态。",
                why_it_matters="复杂任务通常需要多轮状态积累。",
                related=["RAG", "向量数据库"],
                evidence_ids=["EV-1"],
            ),
            DomainConcept(
                name="规划",
                definition="把目标拆成步骤并选择执行顺序。",
                why_it_matters="规划能力影响 Agent 处理复杂任务的可靠性。",
                related=["Planner-Executor"],
                evidence_ids=["EV-2"],
            ),
        ],
        architectures=[
            DomainArchitecture(
                name="Planner-Executor",
                summary="先规划再执行，适合多步骤任务。",
                use_cases=["研究任务", "代码生成"],
                strengths=["结构清晰", "便于检查"],
                limitations=["规划错误会级联"],
                evidence_ids=["EV-2"],
            ),
            DomainArchitecture(
                name="Workflow Agent",
                summary="把 Agent 嵌入确定性工作流节点。",
                use_cases=["生产系统", "审批流"],
                strengths=["可控性高"],
                limitations=["灵活性低于开放式 Agent"],
                evidence_ids=["EV-2"],
            ),
        ],
        tools=[
            DomainTool(
                name="LangGraph",
                category="workflow",
                use_case="构建可控的多节点 Agent 工作流。",
                tradeoffs="工程控制强，但需要设计状态和节点边界。",
                evidence_ids=["EV-1"],
            ),
            DomainTool(
                name="OpenAI Agents SDK",
                category="sdk",
                use_case="快速接入工具调用和 Agent 编排。",
                tradeoffs="上手快，但复杂系统仍需要额外架构。",
                evidence_ids=["EV-1"],
            ),
        ],
        trends=["Agent 开发从 demo 转向工程化、评测和生产可观测性。"],
        learning_path=[
            "理解 Agent、工具调用、记忆、规划等基础概念。",
            "比较 Planner-Executor、Workflow Agent、Multi-Agent 等架构。",
            "选择 LangGraph 或 OpenAI Agents SDK 做一个小项目。",
            "补充评测、日志、权限和失败恢复机制。",
        ],
        open_questions=["哪些框架在生产环境最稳定？"],
    )

    overview = _render_domain_overview(_project(), database, ["EV-1", "EV-2"])
    learning = _render_learning_path(_project(), database)

    assert "## 怎么使用这个知识库" in overview
    assert "## 核心概念速览" in overview
    assert "工具调用" in overview
    assert "Planner-Executor" in overview
    assert "## 学习路径" in learning
    assert "完成标志" in learning
    assert len(learning) > 900
