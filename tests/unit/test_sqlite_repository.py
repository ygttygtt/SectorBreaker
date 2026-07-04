from pathlib import Path

from backend.app.schemas import (
    ClaimStrength,
    EvidenceClaim,
    EvidenceItem,
    MarketScope,
    ProjectMode,
    ProjectDocumentCreate,
    ResearchDepth,
    ResearchProjectCreate,
    RunEvent,
    SourceChannel,
    SourcePolicy,
    SourceQuality,
    VerificationStatus,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database
from backend.app.storage.sqlite import list_migration_files


def test_sqlite_migrations_are_discoverable() -> None:
    migrations = list_migration_files()

    assert [migration.name for migration in migrations] == [
        "001_initial.sql",
        "002_artifacts.sql",
        "003_runs.sql",
        "004_workflow_state.sql",
        "005_planning_and_evidence_ledger.sql",
        "006_run_event_progress.sql",
        "007_documents.sql",
        "008_document_segments_and_citations.sql",
        "009_project_mode.sql",
    ]


def test_sqlite_repository_creates_project_and_evidence(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)

    project = repository.create_project(
        ResearchProjectCreate(
            title="AI Agent Tools",
            domain="AI Agent",
            market_scope=MarketScope.MIXED,
            depth=ResearchDepth.STANDARD,
            source_policy=SourcePolicy.RELIABLE_ONLY,
        )
    )
    evidence = EvidenceItem(
        id="EV-001",
        project_id=project.id,
        source_title="AI agent market",
        source_url="https://example.com/ai-agent-market",
        snippet="AI agent adoption is growing.",
        summary="Market source.",
        claims=[EvidenceClaim(claim_id="CL-001", text="AI agent adoption is growing.")],
        source_channel=SourceChannel.SEARCH,
        source_policy=SourcePolicy.RELIABLE_ONLY.value,
        source_quality=SourceQuality.MEDIUM,
        claim_strength=ClaimStrength.OPINION,
        needs_counterevidence=True,
        confidence=0.7,
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
    )

    repository.add_evidence(evidence)

    assert repository.get_project(project.id).domain == "AI Agent"
    assert repository.get_project(project.id).project_mode == ProjectMode.DOMAIN_KNOWLEDGE
    saved = repository.list_evidence(project.id)[0]
    assert repository.get_project(project.id).source_policy == SourcePolicy.RELIABLE_ONLY
    assert saved.source_url == "https://example.com/ai-agent-market"
    assert saved.source_quality == SourceQuality.MEDIUM
    assert saved.needs_counterevidence is True
    assert saved.claims[0].claim_id == "CL-001"


def test_sqlite_repository_persists_talent_demand_project_mode(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)

    project = repository.create_project(
        ResearchProjectCreate(
            title="LLM Talent Demand",
            domain="大模型应用开发工程师",
            market_scope=MarketScope.CHINA,
            depth=ResearchDepth.QUICK,
            project_mode=ProjectMode.TALENT_DEMAND,
        )
    )

    fetched = repository.get_project(project.id)
    listed = repository.list_projects()[0]

    assert fetched.project_mode == ProjectMode.TALENT_DEMAND
    assert listed.project_mode == ProjectMode.TALENT_DEMAND


def test_sqlite_repository_fts_searches_evidence(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(
        ResearchProjectCreate(
            title="Pet Services",
            domain="宠物服务",
            market_scope=MarketScope.CHINA,
            depth=ResearchDepth.QUICK,
        )
    )
    repository.add_evidence(
        EvidenceItem(
            id="EV-002",
            project_id=project.id,
            source_title="Pet care demand",
            source_url="https://example.com/pet-care",
            snippet="Premium pet care demand is rising.",
            confidence=0.6,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        )
    )

    results = repository.search_project(project.id, "premium", limit=3)

    assert results[0].document_id == "EV-002"


def test_sqlite_repository_stores_documents(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(
        ResearchProjectCreate(
            title="AI Reports",
            domain="AI 报告",
            market_scope=MarketScope.MIXED,
            depth=ResearchDepth.QUICK,
        )
    )

    document = repository.add_document(
        project.id,
        ProjectDocumentCreate(
            channel="assistant_brief",
            content="来源：https://example.com/report\n\n这是一份外部 AI 调研报告。",
            file_name="report.md",
            mime_type="text/markdown",
        ),
    )

    listed = repository.list_documents(project.id)
    fetched = repository.get_document(document.id)
    segments = repository.list_document_segments(document.id)
    citations = repository.list_document_citations(document.id)

    assert listed[0].id == document.id
    assert fetched.file_name == "report.md"
    assert fetched.citation_count == 1
    assert segments
    assert citations[0].source_url == "https://example.com/report"


def test_sqlite_repository_replaces_existing_evidence_by_id(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(
        ResearchProjectCreate(
            title="Evidence Replace",
            domain="证据替换",
            market_scope=MarketScope.MIXED,
            depth=ResearchDepth.QUICK,
        )
    )

    repository.add_evidence(
        EvidenceItem(
            id="EV-REPLACE-001",
            project_id=project.id,
            source_title="Old title",
            source_url="https://example.com/old",
            snippet="old snippet",
            confidence=0.4,
            verification_status=VerificationStatus.UNVERIFIED,
        )
    )
    repository.add_evidence(
        EvidenceItem(
            id="EV-REPLACE-001",
            project_id=project.id,
            source_title="New title",
            source_url="https://example.com/new",
            snippet="new snippet",
            confidence=0.9,
            verification_status=VerificationStatus.VERIFIED,
        )
    )

    saved = repository.get_evidence("EV-REPLACE-001")

    assert saved.source_title == "New title"
    assert saved.source_url == "https://example.com/new"
    assert saved.confidence == 0.9


def test_sqlite_repository_returns_run_events_with_database_cursor(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(
        ResearchProjectCreate(
            title="Event Cursor",
            domain="事件游标",
            market_scope=MarketScope.MIXED,
            depth=ResearchDepth.QUICK,
        )
    )
    run = repository.create_run(project.id)

    first_id = repository.add_run_event(
        RunEvent(event_type="node_started", gate="source_collection", message="开始收集"),
        run.id,
    )
    second_id = repository.add_run_event(
        RunEvent(event_type="node_completed", gate="source_collection", message="收集完成"),
        run.id,
    )

    records = repository.list_run_event_records(run.id, after_id=first_id)

    assert first_id < second_id
    assert [(record_id, event.message) for record_id, event in records] == [(second_id, "收集完成")]
