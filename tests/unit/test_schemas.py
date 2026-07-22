from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.app.schemas import (
    Artifact,
    ArtifactType,
    EvidenceItem,
    MarketScope,
    ProjectSourcePreferences,
    ResearchDepth,
    ResearchFrameOutput,
    ResearchGate,
    ResearchProjectCreate,
    ResearchState,
    SourceEnforcement,
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


def test_project_create_rejects_retired_enterprise_mode() -> None:
    with pytest.raises(ValidationError):
        ResearchProjectCreate(
            title="Retired enterprise mode",
            domain="knowledge management",
            market_scope=MarketScope.CHINA,
            depth=ResearchDepth.QUICK,
            project_mode="talent_demand",
        )


def test_project_source_preferences_validate_domains_and_required_allow_list() -> None:
    with pytest.raises(ValidationError, match="invalid domain"):
        ProjectSourcePreferences(custom_allowed_domains=["https://example.com/path"])

    with pytest.raises(ValidationError, match="needs a source pack"):
        ProjectSourcePreferences(enforcement=SourceEnforcement.REQUIRE)


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


def test_research_frame_output_preserves_sections_when_questions_are_dicts() -> None:
    frame = ResearchFrameOutput.model_validate(
        {
            "sections": ["行业边界", "市场现状", "交易单位"],
            "key_questions": [
                {"importance": "用户为什么付费？", "source": "公开数据"},
                {"question": "信任资产是什么？"},
            ],
        }
    )

    assert frame.sections == ["行业边界", "市场现状", "交易单位"]
    assert frame.key_questions == ["用户为什么付费？", "信任资产是什么？"]
