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
        source_title="RAG 岗位样本",
        source_url="https://example.com/rag",
        source_type="web",
        source_channel=SourceChannel.BOSS_JOB,
        snippet="岗位要求熟悉 RAG、向量数据库和 LangGraph。",
        source_quality=SourceQuality.MEDIUM,
        claim_strength=ClaimStrength.FACT,
        confidence=0.7,
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
    ))
    repository.add_artifact(Artifact(
        id="ART-SKILL-RAG",
        project_id=project.id,
        artifact_type=ArtifactType.TALENT_SKILL_MATRIX,
        title="技能需求矩阵",
        content_path="02-技能需求矩阵.md",
        content="RAG 是高频技能，常与向量数据库、Agent 工程化一起出现。",
        source_evidence_ids=["EV-RAG-1"],
        schema_version="talent-v1",
    ))

    results = ProjectRetriever(repository).retrieve(project.id, "RAG 向量数据库", limit=5)

    ids = {item.source_id for item in results}
    assert "EV-RAG-1" in ids
    assert "ART-SKILL-RAG" in ids
    assert results[0].score >= results[-1].score

