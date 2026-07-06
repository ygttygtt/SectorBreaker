"""Artifact schemas."""

from datetime import UTC, datetime
from enum import StrEnum

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
    # V1.3 talent-demand intelligence
    TALENT_DEMAND_OVERVIEW = "talent_demand_overview"
    TALENT_ROLE_PROFILE = "talent_role_profile"
    TALENT_SKILL_MATRIX = "talent_skill_matrix"
    TALENT_COMPANY_DISTRIBUTION = "talent_company_distribution"
    TALENT_SALARY_EXPERIENCE = "talent_salary_experience"
    TALENT_CAPABILITY_MODEL = "talent_capability_model"
    TALENT_PORTFOLIO_REQUIREMENTS = "talent_portfolio_requirements"
    TALENT_UNRESOLVED_QUESTIONS = "talent_unresolved_questions"
    # Living knowledge-base growth
    FOLLOW_UP_NOTE = "follow_up_note"


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
