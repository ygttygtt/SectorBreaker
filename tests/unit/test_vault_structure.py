"""Tests for vault export directory structure (docs/ + cards/)."""
from __future__ import annotations

from pathlib import Path
from datetime import UTC, datetime

from backend.app.exporters.markdown import _resolve_artifact_export_path
from backend.app.schemas import Artifact, ArtifactType


def _make_main_doc(idx: int) -> Artifact:
    return Artifact(
        id=f"ART-KERNEL-L{idx}-abc{idx:03d}",
        project_id="proj-test",
        artifact_type=ArtifactType.DOMAIN_OVERVIEW,
        title=f"Main Document {idx}",
        content_path=f"0{idx}-main-doc-{idx}.md",
        content="# Main Doc\n\n## Section One\n\nContent here.\n\n## Section Two\n\nMore content.",
        schema_version="v2-agent-kernel",
        created_at=datetime.now(UTC),
    )


def _make_card(idx: int) -> Artifact:
    return Artifact(
        id=f"ART-KERNEL-CARD-xyz{idx:03d}",
        project_id="proj-test",
        artifact_type=ArtifactType.CORE_CONCEPTS,
        title=f"Explainer Card {idx}",
        content_path=f"concept-{idx}.md",
        content="# Card\n\nExplanation here.",
        schema_version="v2-agent-kernel",
        created_at=datetime.now(UTC),
    )


def _make_legacy_doc() -> Artifact:
    return Artifact(
        id="ART-V1-OVERVIEW-abc001",
        project_id="proj-test",
        artifact_type=ArtifactType.DOMAIN_OVERVIEW,
        title="Legacy Doc",
        content_path="legacy-doc.md",
        content="# Legacy",
        schema_version="v1",
        created_at=datetime.now(UTC),
    )


def test_main_docs_export_to_docs_subdir(tmp_path: Path) -> None:
    artifact = _make_main_doc(1)
    resolved = _resolve_artifact_export_path(artifact, tmp_path)
    assert resolved.parent.name == "docs", f"Expected 'docs', got '{resolved.parent.name}'"


def test_card_artifacts_export_to_cards_subdir(tmp_path: Path) -> None:
    artifact = _make_card(1)
    resolved = _resolve_artifact_export_path(artifact, tmp_path)
    assert resolved.parent.name == "cards", f"Expected 'cards', got '{resolved.parent.name}'"


def test_legacy_artifacts_keep_original_path(tmp_path: Path) -> None:
    artifact = _make_legacy_doc()
    resolved = _resolve_artifact_export_path(artifact, tmp_path)
    assert resolved == tmp_path / "legacy-doc.md"
