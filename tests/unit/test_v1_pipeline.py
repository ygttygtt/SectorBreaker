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
    V1KnowledgeContent,
    _build_knowledge_content,
    _evidence_brief,
    _evidence_lines,
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

    assert len(search_provider.queries) == 2
    assert search_provider.queries[0].allowed_domains
    assert search_provider.queries[1].allowed_domains == []
    assert len(repository.evidence) == 1
    assert repository.evidence[0].source_title == "AI Agent framework trends 2026"


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
