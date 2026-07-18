from pathlib import Path

from backend.app.rag import ProjectRetriever
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ClaimStrength,
    EvidenceItem,
    MarketScope,
    ResearchDepth,
    ResearchProjectCreate,
    SourceChannel,
    SourceQuality,
    VerificationStatus,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database


def test_project_retriever_searches_evidence_and_artifacts(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(
        ResearchProjectCreate(
            title="AI Agent 工程师需求",
            domain="AI Agent 工程师",
            market_scope=MarketScope.CHINA,
            depth=ResearchDepth.QUICK,
        )
    )
    repository.add_evidence(EvidenceItem(
        id="EV-RAG-1",
        project_id=project.id,
        source_title="RAG 实践资料",
        source_url="https://example.com/rag",
        source_type="web",
        source_channel=SourceChannel.USER_UPLOAD,
        snippet="RAG 实践需要理解向量数据库、LangGraph 和证据追溯。",
        source_quality=SourceQuality.MEDIUM,
        claim_strength=ClaimStrength.FACT,
        confidence=0.7,
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
    ))
    repository.add_artifact(Artifact(
        id="ART-KNOWLEDGE-RAG",
        project_id=project.id,
        artifact_type=ArtifactType.CORE_CONCEPTS,
        title="RAG 核心概念",
        content_path="concepts/RAG.md",
        content="RAG 常与向量数据库、Agent 工程化和可追溯证据链一起出现。",
        source_evidence_ids=["EV-RAG-1"],
        schema_version="v3-knowledge-ops",
    ))

    results = ProjectRetriever(repository).retrieve(project.id, "RAG 向量数据库", limit=5)

    ids = {item.source_id for item in results}
    assert "EV-RAG-1" in ids
    assert "ART-KNOWLEDGE-RAG" in ids
    assert results[0].score >= results[-1].score
