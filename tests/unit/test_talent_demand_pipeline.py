import asyncio
from pathlib import Path

from backend.app.providers.fakes import FakeSearchProvider
from backend.app.providers.interfaces import JobPostingSource, JobSourceQuery, JobSourceStatus
from backend.app.schemas import MarketScope, ProjectMode, ProjectDocumentCreate, ResearchDepth, ResearchProjectCreate
from backend.app.storage.sqlite import SQLiteRepository, init_database
from backend.app.talent_demand.pipeline import run_talent_demand_pipeline


class FakeJobSourceProvider:
    def __init__(self, jobs: list[JobPostingSource], available: bool = True) -> None:
        self.jobs = jobs
        self.available = available
        self.requests: list[JobSourceQuery] = []

    async def status(self) -> JobSourceStatus:
        return JobSourceStatus(
            provider="fake_boss",
            configured=True,
            available=self.available,
            message="fake ready" if self.available else "fake unavailable",
        )

    async def search_jobs(self, query: JobSourceQuery) -> list[JobPostingSource]:
        self.requests.append(query)
        return self.jobs[: query.limit]


def test_talent_demand_pipeline_uses_uploaded_jd_and_persists_artifacts(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(
        ResearchProjectCreate(
            title="大模型应用开发工程师需求",
            domain="大模型应用开发工程师",
            market_scope=MarketScope.CHINA,
            depth=ResearchDepth.QUICK,
            project_mode=ProjectMode.TALENT_DEMAND,
        )
    )
    repository.add_document(
        project.id,
        ProjectDocumentCreate(
            channel="user_upload",
            file_name="jd.md",
            mime_type="text/markdown",
            content=(
                "岗位：大模型应用开发工程师\n"
                "公司：示例科技\n"
                "地点：北京\n"
                "薪资：20-35K·14薪\n"
                "经验要求：3-5年\n"
                "职责：\n"
                "1. 负责 RAG 知识库和 Agent 应用开发。\n"
                "要求：熟悉 Python、LangGraph、FastAPI 和向量数据库。"
            ),
        ),
    )
    events = []

    async def emit(event):
        events.append(event)

    artifacts = asyncio.run(
        run_talent_demand_pipeline(
            project=project,
            repository=repository,
            search_provider=None,
            llm_provider=None,
            emit=emit,
        )
    )

    paths = {artifact.content_path for artifact in artifacts}
    persisted_paths = {artifact.content_path for artifact in repository.list_artifacts(project.id)}
    evidence = repository.list_evidence(project.id)

    assert "00-岗位需求总览.md" in paths
    assert "02-技能需求矩阵.md" in paths
    assert "skills/RAG.md" in paths
    assert paths == persisted_paths
    assert evidence[0].source_channel.value == "user_upload"
    assert any(event.gate == "source_coverage" and event.data for event in events)


def test_talent_demand_pipeline_supplements_thin_materials_with_search(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(
        ResearchProjectCreate(
            title="AI Agent 工程师需求",
            domain="AI Agent 工程师",
            market_scope=MarketScope.MIXED,
            depth=ResearchDepth.QUICK,
            project_mode=ProjectMode.TALENT_DEMAND,
        )
    )
    search_provider = FakeSearchProvider(
        results=[
            {
                "title": "AI Agent Engineer JD",
                "url": "https://example.com/agent-jd",
                "snippet": "岗位：AI Agent 工程师 薪资：30-45K 经验要求：5年 要求：熟悉 Agent、Python、LangGraph。",
            }
        ]
    )

    asyncio.run(
        run_talent_demand_pipeline(
            project=project,
            repository=repository,
            search_provider=search_provider,
            llm_provider=None,
        )
    )

    evidence = repository.list_evidence(project.id)
    artifacts = repository.list_artifacts(project.id)

    assert search_provider.search_requests
    assert evidence[0].source_channel.value == "search"
    assert any(artifact.content_path == "skills/Agent.md" for artifact in artifacts)


def test_talent_demand_pipeline_ingests_boss_job_source_before_search(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(
        ResearchProjectCreate(
            title="AI Agent 工程师需求",
            domain="AI Agent 工程师",
            market_scope=MarketScope.CHINA,
            depth=ResearchDepth.QUICK,
            project_mode=ProjectMode.TALENT_DEMAND,
        )
    )
    job_provider = FakeJobSourceProvider([
        JobPostingSource(
            title="AI Agent 工程师",
            company="示例科技",
            location="北京",
            salary_text="25-40K",
            experience_text="3-5年",
            description="负责 RAG、Agent、LangGraph 和 Python 后端开发。",
            skills=["RAG", "Agent", "LangGraph", "Python"],
            url="https://example.com/boss-job",
            source_provider="fake_boss",
        )
    ])
    search_provider = FakeSearchProvider(results=[])
    events = []

    async def emit(event):
        events.append(event)

    asyncio.run(
        run_talent_demand_pipeline(
            project=project,
            repository=repository,
            search_provider=search_provider,
            llm_provider=None,
            job_source_provider=job_provider,
            job_source_query=JobSourceQuery(keyword="AI Agent 工程师", city="北京", limit=3),
            emit=emit,
        )
    )

    evidence = repository.list_evidence(project.id)
    coverage_event = next(
        event for event in events
        if event.gate == "source_coverage" and event.event_type == "node_completed"
    )

    assert job_provider.requests
    assert evidence[0].source_channel.value == "boss_job"
    assert "RAG" in evidence[0].snippet
    assert coverage_event.data["boss_job_count"] == 1
    assert any(event.gate == "boss_job_intake" for event in events)
