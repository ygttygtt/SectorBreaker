from pathlib import Path

from backend.app.schemas import (
    ClaimStrength,
    EvidenceClaim,
    EvidenceItem,
    MarketScope,
    ResearchDepth,
    ResearchProjectCreate,
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
    saved = repository.list_evidence(project.id)[0]
    assert repository.get_project(project.id).source_policy == SourcePolicy.RELIABLE_ONLY
    assert saved.source_url == "https://example.com/ai-agent-market"
    assert saved.source_quality == SourceQuality.MEDIUM
    assert saved.needs_counterevidence is True
    assert saved.claims[0].claim_id == "CL-001"


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
