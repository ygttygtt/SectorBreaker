import asyncio
from datetime import UTC, datetime

from backend.app.providers.interfaces import SearchQuery, SearchResult
from backend.app.schemas import MarketScope, ProjectStatus, ResearchDepth, ResearchProject, SourcePolicy
from backend.app.legacy.legacy_fixed_v2_pipeline import run_v2_react_knowledge_pipeline


def _project() -> ResearchProject:
    return ResearchProject(
        id="project-v2",
        title="Agent开发",
        domain="Agent开发",
        market_scope=MarketScope.MIXED,
        source_policy=SourcePolicy.OPEN_WEB,
        depth=ResearchDepth.QUICK,
        status=ProjectStatus.DRAFT,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_v2_pipeline_runs_layered_react_and_creates_artifacts() -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.evidence = []
            self.artifacts = []

        def list_evidence(self, project_id: str):
            return []

        def list_documents(self, project_id: str):
            return []

        def add_evidence(self, item):
            self.evidence.append(item)

        def add_artifact(self, artifact):
            self.artifacts.append(artifact)

    class LayeredSearch:
        def __init__(self) -> None:
            self.queries: list[SearchQuery] = []

        async def search(self, query: SearchQuery) -> list[SearchResult]:
            self.queries.append(query)
            index = len(self.queries)
            return [
                SearchResult(
                    title=f"AI Agent development layer {index}",
                    url=f"https://example.com/agent-v2-{index}",
                    snippet=(
                        "AI Agent development involves tools, workflow orchestration, "
                        "frameworks, users, risk governance, evaluation, and production deployment."
                    ),
                )
            ]

    repository = FakeRepository()
    search = LayeredSearch()
    events = []

    async def emit(event):
        events.append(event)

    artifacts = asyncio.run(
        run_v2_react_knowledge_pipeline(
            project=_project(),
            repository=repository,  # type: ignore[arg-type]
            search_provider=search,
            llm_provider=None,
            emit=emit,
        )
    )

    assert len(search.queries) >= 5
    assert repository.evidence
    assert artifacts
    assert repository.artifacts == artifacts
    assert any(event.gate == "specialist_react_loop" for event in events)
    assert any(event.gate == "coverage_evaluation" for event in events)
