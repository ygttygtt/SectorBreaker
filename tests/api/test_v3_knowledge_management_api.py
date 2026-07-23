from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agent_kernel.models import KernelRunResult, KernelRunStatus
from backend.app.api.app import _finalize_kernel_run, create_app
from backend.app.schemas import (
    EvidenceItem,
    MarketScope,
    ResearchDepth,
    ResearchProjectCreate,
    RunStatus,
    SourcePolicy,
    VerificationStatus,
)
from backend.app.storage.sqlite import SQLiteRepository, init_database


def _create_project(client: TestClient) -> str:
    response = client.post("/api/projects", json={
        "title": "Managed Knowledge Vault",
        "domain": "RAG",
        "market_scope": "mixed",
        "depth": "quick",
        "source_policy": "user_materials_only",
    })
    assert response.status_code == 200
    return response.json()["id"]


def test_v3_vault_audit_changeset_apply_restart_and_rollback(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    export_root = tmp_path / "exports"
    client = TestClient(create_app(database_path=database_path, export_root=export_root))
    project_id = _create_project(client)
    SQLiteRepository(database_path).add_evidence(EvidenceItem(
        id="EV-LOCAL-001",
        project_id=project_id,
        source_title="Local acceptance source",
        snippet="A controlled evidence record for the vault lifecycle.",
        source_url="https://example.com/local-acceptance",
        confidence=0.7,
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
    ))

    vault = tmp_path / "source-vault"
    vault.mkdir()
    original = "---\nevidence_ids: []\n---\n# RAG\n\nTODO: add a cited retrieval explanation.\n"
    (vault / "RAG.md").write_bytes(original.encode("utf-8"))

    imported = client.post(
        f"/api/projects/{project_id}/vault/import",
        json={"source_path": str(vault)},
    )
    assert imported.status_code == 200
    assert imported.json()["imported_paths"] == ["RAG.md"]

    audited = client.post(f"/api/projects/{project_id}/audits")
    assert audited.status_code == 200
    assert audited.json()["metrics"]["findings"] >= 1
    backlog = client.get(f"/api/projects/{project_id}/maintenance-backlog")
    assert backlog.status_code == 200
    assert backlog.json()

    updated = (
        "---\nevidence_ids: [EV-LOCAL-001]\n---\n# RAG\n\n"
        "Retrieval combines indexed project memory with evidence-linked notes. [^EV-LOCAL-001]\n"
    )
    proposed = client.post(f"/api/projects/{project_id}/change-sets", json={
        "task_id": backlog.json()[0]["id"],
        "summary": "replace unresolved marker with a cited explanation",
        "path": "RAG.md",
        "after_content": updated,
        "evidence_ids": ["EV-LOCAL-001"],
        "factual_change": True,
    })
    assert proposed.status_code == 200
    change_set_id = proposed.json()["id"]
    assert proposed.json()["operations"][0]["unified_diff"]

    assert client.post(
        f"/api/projects/{project_id}/change-sets/{change_set_id}/approve"
    ).json()["status"] == "approved"
    assert client.post(
        f"/api/projects/{project_id}/change-sets/{change_set_id}/apply"
    ).json()["status"] == "applied"
    exported = client.post(f"/api/projects/{project_id}/exports")
    assert exported.status_code == 200
    export_dir = Path(exported.json()["export_dir"])
    exported_note = (export_dir / "RAG.md").read_text(encoding="utf-8")
    assert 'schema_version: "v3-knowledge-ops"' in exported_note
    assert "Retrieval combines indexed project memory" in exported_note
    assert (export_dir / ".sectorbreaker" / "health_snapshot.json").exists()
    assert (export_dir / ".sectorbreaker" / "maintenance_backlog.json").exists()
    assert (export_dir / ".sectorbreaker" / "change_sets.json").exists()

    restarted = TestClient(create_app(database_path=database_path, export_root=export_root))
    active_note = restarted.get(f"/api/projects/{project_id}/vault").json()["notes"][0]
    assert active_note["revision"] == 2

    rolled_back = restarted.post(
        f"/api/projects/{project_id}/change-sets/{change_set_id}/rollback"
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "rolled_back"
    restored = restarted.get(f"/api/projects/{project_id}/vault").json()["notes"][0]
    assert restored["revision"] == 3
    active_artifacts = restarted.get(f"/api/projects/{project_id}/artifacts").json()
    assert active_artifacts[0]["content"] == original
    reexported = restarted.post(f"/api/projects/{project_id}/exports")
    assert reexported.status_code == 200
    restored_note = (Path(reexported.json()["export_dir"]) / "RAG.md").read_text(encoding="utf-8")
    assert "TODO: add a cited retrieval explanation." in restored_note
    assert "Retrieval combines indexed project memory" not in restored_note


def test_v3_rejects_retired_enterprise_project_mode_and_routes(tmp_path: Path) -> None:
    client = TestClient(create_app(
        database_path=tmp_path / "sectorbreaker.sqlite3",
        export_root=tmp_path / "exports",
    ))
    response = client.post("/api/projects", json={
        "title": "Retired Mode",
        "domain": "Hiring",
        "market_scope": "mixed",
        "depth": "quick",
        "project_mode": "talent_demand",
    })
    assert response.status_code == 422
    assert client.get("/api/config/job-source").status_code == 404


def test_kernel_waiting_for_review_is_not_reported_as_completed(tmp_path: Path) -> None:
    database_path = tmp_path / "status.sqlite3"
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    project = repository.create_project(ResearchProjectCreate(
        title="Review Status",
        domain="RAG",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
        source_policy=SourcePolicy.USER_MATERIALS_ONLY,
    ))
    run = repository.create_claimed_run(
        project.id,
        lease_owner_id="worker-test",
        lease_seconds=60,
    )

    _finalize_kernel_run(repository, run.id, KernelRunResult(
        status=KernelRunStatus.WAITING_FOR_HUMAN,
        state_version="3",
        stop_reason="ChangeSet requires review",
    ), lease_owner_id="worker-test")

    persisted = repository.get_run(run.id)
    assert persisted.status == RunStatus.WAITING_FOR_HUMAN
    assert persisted.current_gate == "human_feedback"
    assert persisted.completed_at is None
