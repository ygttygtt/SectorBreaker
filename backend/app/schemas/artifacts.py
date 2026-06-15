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
