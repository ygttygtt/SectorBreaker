from pathlib import Path

from backend.app.rag import ProjectRetriever
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    MarketScope,
    ResearchDepth,
    ResearchProjectCreate,
    SourcePolicy,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database


def test_retrieval_excludes_superseded_revision_and_returns_hit_local_snippet(tmp_path: Path) -> None:
    database_path = tmp_path / "retrieval.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(ResearchProjectCreate(
        title="Revision Retrieval",
        domain="RAG",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
        source_policy=SourcePolicy.USER_MATERIALS_ONLY,
    ))
    old = Artifact(
        id="ART-OLD",
        project_id=project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="RAG",
        content_path="RAG.md",
        content="# RAG\n\nlegacy_unique_phrase should never be retrieved after supersession.",
        schema_version="v3-knowledge-ops",
    )
    repository.add_artifact(old)
    padding = "unrelated introduction " * 40
    new = Artifact(
        id="ART-NEW",
        project_id=project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="RAG",
        content_path="RAG.md",
        content=f"# RAG\n\n{padding}\nhybrid retrieval combines lexical and vector rankings.",
        schema_version="v3-knowledge-ops",
        supersedes=old.id,
    )
    repository.add_artifact(new)

    retriever = ProjectRetriever(repository)
    assert all(hit.source_id != old.id for hit in retriever.retrieve(project.id, "legacy_unique_phrase"))
    hits = retriever.retrieve(project.id, "hybrid retrieval")
    artifact_hit = next(hit for hit in hits if hit.source_id == new.id)
    assert "hybrid retrieval" in artifact_hit.snippet
    assert artifact_hit.relative_path == "RAG.md"
    assert artifact_hit.content_hash == new.content_hash
