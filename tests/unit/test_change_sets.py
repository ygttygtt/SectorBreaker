from pathlib import Path

from backend.app.knowledge_base import ChangeSetService, VaultKnowledgeService
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ChangeOperation,
    ChangeOperationType,
    ChangeSet,
    ChangeSetProposalRequest,
    ChangeSetStatus,
    MarketScope,
    ResearchDepth,
    ResearchProjectCreate,
    SourcePolicy,
    VaultImportRequest,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database


def _setup(tmp_path: Path):
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(ResearchProjectCreate(
        title="Change Vault",
        domain="RAG",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
        source_policy=SourcePolicy.USER_MATERIALS_ONLY,
    ))
    vault = tmp_path / "vault"
    vault.mkdir()
    original = "---\nevidence_ids: []\n---\n# RAG\n\nOriginal content.\n"
    (vault / "RAG.md").write_bytes(original.encode("utf-8"))
    VaultKnowledgeService(repository).import_vault(project, VaultImportRequest(source_path=str(vault)))
    return repository, project, original


def test_apply_and_rollback_change_set_preserves_history(tmp_path: Path) -> None:
    repository, project, original = _setup(tmp_path)
    service = ChangeSetService(repository)
    updated = "---\nevidence_ids: [EV-001]\n---\n# RAG\n\nUpdated with evidence. [^EV-001]\n"
    change_set = service.propose(
        project.id,
        ChangeSetProposalRequest(
            summary="补充证据",
            path="RAG.md",
            after_content=updated,
            evidence_ids=["EV-001"],
            factual_change=True,
        ),
        run_id="run-origin",
    )
    service.approve(change_set.id)
    applied = service.apply(change_set.id)

    assert applied.status == ChangeSetStatus.APPLIED
    assert repository.list_artifacts(project.id)[0].content == updated
    history = repository.list_artifact_history(project.id, "RAG.md")
    assert len(history) == 2
    assert history[0].active is False
    assert history[0].superseded_by == history[1].id
    assert history[1].supersedes == history[0].id
    assert history[1].run_id == "run-origin"
    assert applied.origin_run_id == "run-origin"

    rolled_back = service.rollback(change_set.id)
    assert rolled_back.status == ChangeSetStatus.ROLLED_BACK
    assert repository.list_artifacts(project.id)[0].content == original
    assert len(repository.list_artifact_history(project.id, "RAG.md")) == 3


def test_apply_detects_base_hash_conflict(tmp_path: Path) -> None:
    repository, project, _ = _setup(tmp_path)
    service = ChangeSetService(repository)
    change_set = service.propose(project.id, ChangeSetProposalRequest(
        summary="planned update",
        path="RAG.md",
        after_content="# planned update",
    ))
    current = repository.list_artifacts(project.id)[0]
    repository.add_artifact(Artifact(
        id="ART-CONCURRENT",
        project_id=project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="RAG",
        content_path="RAG.md",
        content="# user changed this note",
        schema_version="v3-knowledge-ops",
        supersedes=current.id,
    ))
    service.approve(change_set.id)
    conflicted = service.apply(change_set.id)
    assert conflicted.status == ChangeSetStatus.CONFLICTED
    assert repository.list_artifacts(project.id)[0].id == "ART-CONCURRENT"


def test_multi_operation_conflict_writes_nothing(tmp_path: Path) -> None:
    repository, project, _ = _setup(tmp_path)
    active = repository.list_artifacts(project.id)[0]
    change_set = ChangeSet(
        id="CS-ATOMIC",
        project_id=project.id,
        status=ChangeSetStatus.APPROVED,
        summary="one valid create followed by one stale update",
        operations=[
            ChangeOperation(
                operation=ChangeOperationType.CREATE,
                path="cards/new.md",
                after_content="# New Card",
            ),
            ChangeOperation(
                operation=ChangeOperationType.UPDATE,
                path=active.content_path,
                base_hash="sha256:stale",
                before_content=active.content,
                after_content="# stale update",
            ),
        ],
    )
    repository.save_change_set(change_set)

    result = ChangeSetService(repository).apply(change_set.id)

    assert result.status == ChangeSetStatus.CONFLICTED
    assert [item.content_path for item in repository.list_artifacts(project.id)] == ["RAG.md"]
