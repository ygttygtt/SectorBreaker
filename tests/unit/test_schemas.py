from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.app.schemas import (
    Artifact,
    ArtifactType,
    EvidenceItem,
    MarketScope,
    ResearchDepth,
    ResearchGate,
    ResearchProjectCreate,
    ResearchState,
    VerificationStatus,
)


def test_project_create_normalizes_domain_and_defaults() -> None:
    project = ResearchProjectCreate(
        title="AI Agent Tools",
        domain="  AI Agent 工具  ",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )

    assert project.domain == "AI Agent 工具"
    assert project.market_scope == MarketScope.MIXED
    assert project.depth == ResearchDepth.QUICK


def test_verified_evidence_requires_source_url() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            id="EV-001",
            project_id="project-1",
            source_title="Example",
            snippet="Market is growing.",
            verification_status=VerificationStatus.VERIFIED,
            confidence=0.8,
        )


def test_research_state_requires_supported_claims_for_export_gate() -> None:
    artifact = Artifact(
        id="ART-001",
        project_id="project-1",
        artifact_type=ArtifactType.OPPORTUNITY_MAP,
        title="Opportunity map",
        content_path="exports/project/05-机会地图/index.md",
        source_evidence_ids=[],
        created_at=datetime.now(UTC),
    )

    with pytest.raises(ValidationError):
        ResearchState(
            project_id="project-1",
            current_gate=ResearchGate.EXPORT,
            artifacts=[artifact],
        )

