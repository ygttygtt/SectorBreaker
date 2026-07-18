from pathlib import Path

from backend.app.knowledge_base import VaultKnowledgeService
from backend.app.schemas import (
    MarketScope,
    ResearchDepth,
    ResearchProjectCreate,
    SourcePolicy,
    VaultImportRequest,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database


def _repository(tmp_path: Path) -> SQLiteRepository:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    return SQLiteRepository(database_path)


def _project(repository: SQLiteRepository):
    return repository.create_project(ResearchProjectCreate(
        title="Managed Vault",
        domain="知识管理",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
        source_policy=SourcePolicy.USER_MATERIALS_ONLY,
    ))


def test_import_vault_is_idempotent_and_preserves_paths(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    project = _project(repository)
    vault = tmp_path / "source-vault"
    (vault / "concepts").mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    (vault / "README.md").write_text("---\nevidence_ids: []\n---\n# 首页\n\n[[concepts/RAG]]", encoding="utf-8")
    (vault / "concepts" / "RAG.md").write_text("# RAG\n\n待验证：补充来源。", encoding="utf-8")
    (vault / ".obsidian" / "cache.md").write_text("ignored", encoding="utf-8")

    service = VaultKnowledgeService(repository)
    first = service.import_vault(project, VaultImportRequest(source_path=str(vault)))
    second = service.import_vault(project, VaultImportRequest(source_path=str(vault)))

    assert first.id == second.id
    assert first.note_count == 2
    assert first.imported_paths == ["README.md", "concepts/RAG.md"]
    assert ".obsidian/cache.md" in first.skipped_paths
    assert [item.content_path for item in repository.list_artifacts(project.id)] == [
        "README.md",
        "concepts/RAG.md",
    ]


def test_health_audit_creates_stable_backlog(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    project = _project(repository)
    vault = tmp_path / "audit-vault"
    vault.mkdir()
    (vault / "Home.md").write_text(
        "---\ntitle: Home\nevidence_ids: []\n---\n# Home\n\n[[Known]]\n[[Missing]]",
        encoding="utf-8",
    )
    (vault / "Known.md").write_text("# Known\n\nTODO: add evidence", encoding="utf-8")
    (vault / "Orphan.md").write_text("# Orphan\n\nStandalone note.", encoding="utf-8")
    (vault / "Duplicate A.md").write_text("---\ntitle: Same\n---\n# Same", encoding="utf-8")
    (vault / "Duplicate B.md").write_text("---\ntitle: Same\n---\n# Same", encoding="utf-8")

    service = VaultKnowledgeService(repository)
    service.import_vault(project, VaultImportRequest(source_path=str(vault)))
    first = service.audit(project.id)
    first_tasks = repository.list_maintenance_tasks(project.id)
    second = service.audit(project.id)
    second_tasks = repository.list_maintenance_tasks(project.id)

    assert first.metrics["broken_links"] == 1
    assert first.metrics["duplicate_titles"] == 1
    assert first.metrics["missing_frontmatter"] >= 2
    assert first.metrics["orphan_notes"] >= 1
    assert len(first.findings) == len(second.findings)
    assert {task.fingerprint for task in first_tasks} == {task.fingerprint for task in second_tasks}
