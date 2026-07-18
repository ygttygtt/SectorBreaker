"""Artifact schemas."""

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, Field


class ArtifactType(StrEnum):
    RESEARCH_FRAME = "research_frame"
    INDUSTRY_MAP = "industry_map"
    MARKET_OVERVIEW = "market_overview"
    PLAYER_MAP = "player_map"
    TRANSACTION_UNITS = "transaction_units"
    CONTENT_CHANNELS = "content_channels"
    OPPORTUNITY_MAP = "opportunity_map"
    EXPORT_MANIFEST = "export_manifest"
    # Step 2: Reverse engineering
    COMPETITOR_ANALYSIS = "competitor_analysis"
    REVENUE_STRUCTURE = "revenue_structure"
    CONVERSION_PATH = "conversion_path"
    TRUST_ASSETS = "trust_assets"
    # Step 3: Content ecosystem
    CONTENT_ACCOUNTS = "content_accounts"
    CONTENT_TOPICS = "content_topics"
    CONTENT_CLASSIFICATION = "content_classification"
    # Runnable V1 knowledge system
    DOMAIN_OVERVIEW = "domain_overview"
    LEARNING_PATH = "learning_path"
    CORE_CONCEPTS = "core_concepts"
    PLAYER_TOOL_MAP = "player_tool_map"
    TREND_EVIDENCE = "trend_evidence"
    PROBLEM_OPPORTUNITY_MAP = "problem_opportunity_map"
    UNRESOLVED_QUESTIONS = "unresolved_questions"
    # Living knowledge-base growth
    FOLLOW_UP_NOTE = "follow_up_note"
    VAULT_NOTE = "vault_note"
    KNOWLEDGE_HEALTH_REPORT = "knowledge_health_report"
    KNOWLEDGE_MAINTENANCE_PLAN = "knowledge_maintenance_plan"


class Artifact(BaseModel):
    id: str
    project_id: str
    artifact_type: ArtifactType
    title: str
    content_path: str
    content: str = ""
    source_evidence_ids: list[str] = Field(default_factory=list)
    schema_version: str = "1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revision: int = Field(default=1, ge=1)
    content_hash: str = ""
    active: bool = True
    supersedes: str | None = None
    superseded_by: str | None = None  # ID of the artifact that supersedes this one
    run_id: str | None = None
    change_set_id: str | None = None

    def model_post_init(self, __context) -> None:  # type: ignore[override]
        if not self.content_hash:
            self.content_hash = "sha256:" + sha256(self.content.encode("utf-8")).hexdigest()
