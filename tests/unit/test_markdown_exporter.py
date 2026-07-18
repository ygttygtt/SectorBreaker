import json
from pathlib import Path

import pytest

from backend.app.agent_state import SectorBreakerState
from backend.app.exporters.markdown import MarkdownExporter
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ChangeOperation,
    ChangeOperationType,
    ChangeSet,
    ChangeSetStatus,
    ClaimStrength,
    EvidenceItem,
    FindingSeverity,
    HealthFinding,
    HealthFindingType,
    KnowledgeHealthReport,
    MaintenanceTask,
    MaintenanceTaskStatus,
    MarketScope,
    ResearchDepth,
    ResearchProject,
    RunEvent,
    SourceChannel,
    SourceQuality,
    VerificationStatus,
)


def _project(*, project_id: str = "project-v3", title: str = "Knowledge Ops") -> ResearchProject:
    return ResearchProject(
        id=project_id,
        title=title,
        domain="Autonomous knowledge management",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )


def _evidence(project_id: str) -> EvidenceItem:
    return EvidenceItem(
        id="EV-KERNEL-1",
        project_id=project_id,
        source_title="Knowledge management source",
        source_url="https://example.com/knowledge-ops",
        source_type="web",
        source_channel=SourceChannel.SEARCH,
        snippet="Evidence-linked revisions make knowledge changes inspectable.",
        source_quality=SourceQuality.MEDIUM,
        claim_strength=ClaimStrength.FACT,
        confidence=0.8,
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
    )


def test_markdown_exporter_writes_only_active_v3_revisions_and_preserves_user_properties(tmp_path: Path) -> None:
    project = _project()
    inactive = Artifact(
        id="ART-OLD",
        project_id=project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="Imported Note",
        content_path="notes/imported.md",
        content="# Imported Note\n\nobsolete content",
        schema_version="v3-knowledge-ops",
        active=False,
    )
    active = Artifact(
        id="ART-ACTIVE",
        project_id=project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="Imported Note",
        content_path="notes/imported.md",
        content=(
            "---\n"
            "aliases: [\"Imported Alias\"]\n"
            "tags: [\"personal\", \"reference\"]\n"
            "custom_property: keep-me\n"
            "evidence_ids: [\"EV-USER-1\"]\n"
            "schema_version: \"old-inner-schema\"\n"
            "---\n\n"
            "# Imported Note\n\nactive content"
        ),
        source_evidence_ids=["EV-KERNEL-1"],
        schema_version="v3-knowledge-ops",
        revision=2,
        supersedes=inactive.id,
    )
    main_document = Artifact(
        id="ART-MAIN",
        project_id=project.id,
        artifact_type=ArtifactType.DOMAIN_OVERVIEW,
        title="Knowledge Ops Overview",
        content_path="01-overview.md",
        content="# Knowledge Ops Overview\n\nMain document.",
        source_evidence_ids=["EV-KERNEL-1"],
        schema_version="v3-knowledge-ops",
    )
    card = Artifact(
        id="ART-CARD",
        project_id=project.id,
        artifact_type=ArtifactType.CORE_CONCEPTS,
        title="Evidence Chain",
        content_path="concepts/evidence-chain.md",
        content="# Evidence Chain\n\nCard content.",
        source_evidence_ids=["EV-KERNEL-1"],
        schema_version="v2-agent-kernel-card",
    )

    manifest = MarkdownExporter(tmp_path).export_project(
        project,
        [inactive, active, main_document, card],
        [_evidence(project.id)],
    )

    project_dir = tmp_path / "knowledge-ops"
    assert "notes/imported.md" in manifest.artifact_paths
    assert "docs/01-overview.md" in manifest.artifact_paths
    assert "cards/concepts/evidence-chain.md" in manifest.artifact_paths
    assert "sources/evidence-ledger.md" in manifest.artifact_paths
    assert len(manifest.active_artifacts) == 3
    assert {item["id"] for item in manifest.active_artifacts} == {"ART-ACTIVE", "ART-MAIN", "ART-CARD"}

    rendered = (project_dir / "notes" / "imported.md").read_text(encoding="utf-8")
    assert rendered.count("\n---") == 1
    assert 'schema_version: "v3-knowledge-ops"' in rendered
    assert "revision: 2" in rendered
    assert f'content_hash: "{active.content_hash}"' in rendered
    assert 'status: "active"' in rendered
    assert 'aliases: ["Imported Alias"]' in rendered
    assert "custom_property: keep-me" in rendered
    assert "personal" in rendered and "reference" in rendered
    assert "EV-KERNEL-1" in rendered and "EV-USER-1" in rendered
    assert "old-inner-schema" not in rendered
    assert "active content" in rendered
    assert "obsolete content" not in rendered

    manifest_payload = json.loads((project_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["export_version"] == "3"
    assert manifest_payload["schema_version"] == "v3-knowledge-ops"
    assert manifest_payload["active_artifacts"][0]["content_hash"].startswith("sha256:")


def test_markdown_exporter_writes_full_state_and_v3_control_plane_bundle(tmp_path: Path) -> None:
    project = _project(project_id="project-control", title="Control Plane")
    artifact = Artifact(
        id="ART-CONTROL",
        project_id=project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="Controlled Note",
        content_path="vault/controlled-note.md",
        content="# Controlled Note\n\nCurrent revision.",
        source_evidence_ids=["EV-KERNEL-1"],
        schema_version="v3-knowledge-ops",
        revision=2,
        supersedes="ART-CONTROL-OLD",
        run_id="run-control",
        change_set_id="CS-CONTROL",
    )
    finding = HealthFinding(
        id="HF-CONTROL",
        finding_type=HealthFindingType.MISSING_EVIDENCE_METADATA,
        severity=FindingSeverity.WARNING,
        target_paths=[artifact.content_path],
        explanation="Missing evidence metadata.",
        suggested_action="Add evidence ids.",
    )
    health = KnowledgeHealthReport(
        id="KHR-CONTROL",
        project_id=project.id,
        snapshot_hash="sha256:health",
        metrics={"active_notes": 1, "findings": 1},
        findings=[finding],
    )
    task = MaintenanceTask(
        id="MT-CONTROL",
        project_id=project.id,
        fingerprint="fingerprint-control",
        finding_ids=[finding.id],
        task_type=finding.finding_type.value,
        objective=finding.suggested_action,
        target_paths=finding.target_paths,
        status=MaintenanceTaskStatus.OPEN,
    )
    operation = ChangeOperation(
        operation=ChangeOperationType.UPDATE,
        path=artifact.content_path,
        base_hash="sha256:before",
        before_content="# Controlled Note\n\nOld revision.",
        after_content=artifact.content,
        unified_diff="--- a/vault/controlled-note.md\n+++ b/vault/controlled-note.md\n",
        factual_change=True,
    )
    change_set = ChangeSet(
        id="CS-CONTROL",
        project_id=project.id,
        task_id=task.id,
        status=ChangeSetStatus.APPLIED,
        summary="Add evidence metadata",
        evidence_ids=["EV-KERNEL-1"],
        operations=[operation],
        applied_artifact_ids=[artifact.id],
    )
    state = SectorBreakerState.initialize(
        project_id=project.id,
        domain=project.domain,
        user_goal="Maintain the vault",
    )
    state.vault_import_id = "VI-CONTROL"

    manifest = MarkdownExporter(tmp_path).export_project(
        project,
        [artifact],
        [_evidence(project.id)],
        run_events=[RunEvent(event_type="change_set_applied", gate="knowledge_maintenance", message="Applied")],
        agent_state=state,
        health_snapshot=health,
        maintenance_backlog=[task],
        change_sets=[change_set],
    )

    expected_control_files = {
        ".sectorbreaker/project.json",
        ".sectorbreaker/agent_state.json",
        ".sectorbreaker/evidence_ledger.json",
        ".sectorbreaker/artifact_manifest.json",
        ".sectorbreaker/health_snapshot.json",
        ".sectorbreaker/maintenance_backlog.json",
        ".sectorbreaker/change_sets.json",
        ".sectorbreaker/open_questions.json",
        ".sectorbreaker/trace_summary.json",
    }
    assert expected_control_files.issubset(set(manifest.artifact_paths))
    assert manifest.latest_health_snapshot_id == health.id
    assert manifest.maintenance_task_summary == {"open": 1}
    assert manifest.change_set_summary == {"applied": 1}

    state_dir = tmp_path / "control-plane" / ".sectorbreaker"
    state_payload = json.loads((state_dir / "agent_state.json").read_text(encoding="utf-8"))
    assert state_payload["state_version"] == "3"
    assert state_payload["meta_context"]["project_id"] == project.id
    assert state_payload["knowledge_schema"]["layers"]
    assert state_payload["autonomy_policy"]["allow_delete"] is False
    assert state_payload["latest_health_report_id"] == health.id
    assert state_payload["maintenance_task_ids"] == [task.id]
    assert state_payload["artifact_memory"][0]["artifact_id"] == artifact.id
    assert state_payload["artifact_memory"][0]["revision"] == 2
    assert "artifact_count" not in state_payload

    health_payload = json.loads((state_dir / "health_snapshot.json").read_text(encoding="utf-8"))
    backlog_payload = json.loads((state_dir / "maintenance_backlog.json").read_text(encoding="utf-8"))
    changes_payload = json.loads((state_dir / "change_sets.json").read_text(encoding="utf-8"))
    artifact_payload = json.loads((state_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    assert health_payload["id"] == health.id
    assert backlog_payload[0]["id"] == task.id
    assert changes_payload[0]["operations"][0]["unified_diff"].startswith("--- a/")
    assert changes_payload[0]["operations"][0]["before_hash"].startswith("sha256:")
    assert changes_payload[0]["operations"][0]["after_hash"] == artifact.content_hash
    assert artifact_payload == [{
        "id": artifact.id,
        "artifact_type": artifact.artifact_type.value,
        "title": artifact.title,
        "content_path": artifact.content_path,
        "source_content_path": artifact.content_path,
        "schema_version": "v3-knowledge-ops",
        "revision": artifact.revision,
        "content_hash": artifact.content_hash,
        "status": "active",
        "supersedes": artifact.supersedes,
        "superseded_by": artifact.superseded_by,
        "run_id": artifact.run_id,
        "change_set_id": artifact.change_set_id,
        "source_evidence_ids": artifact.source_evidence_ids,
        "created_at": artifact.created_at.isoformat(),
    }]


def test_markdown_exporter_synthesizes_full_inspectable_state_without_checkpoint(tmp_path: Path) -> None:
    project = _project(project_id="project-no-checkpoint", title="No Checkpoint")
    artifact = Artifact(
        id="ART-NO-CHECKPOINT",
        project_id=project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="Imported Note",
        content_path="imported.md",
        content="# Imported Note",
        schema_version="v3-knowledge-ops",
    )

    MarkdownExporter(tmp_path).export_project(project, [artifact], [])

    state_path = tmp_path / "no-checkpoint" / ".sectorbreaker" / "agent_state.json"
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["state_version"] == "3"
    assert state_payload["meta_context"]["project_id"] == project.id
    assert state_payload["artifact_memory"][0]["content_hash"] == artifact.content_hash
    health_payload = json.loads(
        (tmp_path / "no-checkpoint" / ".sectorbreaker" / "health_snapshot.json").read_text(encoding="utf-8")
    )
    assert health_payload == {"project_id": project.id, "status": "not_generated", "report": None}


def test_markdown_exporter_copies_default_obsidian_config(tmp_path: Path) -> None:
    project = _project(project_id="project-config", title="Vault Config")
    artifact = Artifact(
        id="ART-CONFIG",
        project_id=project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="Config Note",
        content_path="config-note.md",
        content="# Config Note",
        schema_version="v3-knowledge-ops",
    )

    MarkdownExporter(tmp_path).export_project(project, [artifact], [])

    project_dir = tmp_path / "vault-config"
    assert (project_dir / ".obsidian" / "app.json").exists()
    assert (project_dir / ".obsidian" / "core-plugins.json").exists()


def test_markdown_exporter_rejects_duplicate_active_paths(tmp_path: Path) -> None:
    project = _project()
    artifacts = [
        Artifact(
            id=f"ART-DUP-{index}",
            project_id=project.id,
            artifact_type=ArtifactType.VAULT_NOTE,
            title=f"Duplicate {index}",
            content_path="duplicate.md",
            content=f"# Duplicate {index}",
            schema_version="v3-knowledge-ops",
        )
        for index in (1, 2)
    ]

    with pytest.raises(ValueError, match="multiple active artifacts"):
        MarkdownExporter(tmp_path).export_project(project, artifacts, [])


def test_markdown_exporter_removes_previous_file_when_revision_is_no_longer_active(tmp_path: Path) -> None:
    project = _project(project_id="project-reexport", title="Re Export")
    created_note = Artifact(
        id="ART-CREATED",
        project_id=project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="Created Note",
        content_path="temporary.md",
        content="# Temporary",
        schema_version="v3-knowledge-ops",
    )
    exporter = MarkdownExporter(tmp_path)
    exporter.export_project(project, [created_note], [])
    stale_path = tmp_path / "re-export" / "temporary.md"
    assert stale_path.exists()

    created_note.active = False
    exporter.export_project(project, [created_note], [])

    assert not stale_path.exists()
    artifact_manifest = json.loads(
        (tmp_path / "re-export" / ".sectorbreaker" / "artifact_manifest.json").read_text(encoding="utf-8")
    )
    assert artifact_manifest == []


def test_markdown_exporter_rejects_unsafe_artifact_path(tmp_path: Path) -> None:
    project = _project()
    artifact = Artifact(
        id="ART-UNSAFE",
        project_id=project.id,
        artifact_type=ArtifactType.VAULT_NOTE,
        title="Unsafe",
        content_path="../outside.md",
        content="# Unsafe",
        schema_version="v3-knowledge-ops",
    )

    with pytest.raises(ValueError, match="safe relative path"):
        MarkdownExporter(tmp_path).export_project(project, [artifact], [])
