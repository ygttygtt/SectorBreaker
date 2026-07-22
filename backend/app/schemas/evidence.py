"""Evidence schemas."""

from datetime import datetime
from typing import Any

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"


class SourceType(StrEnum):
    OFFICIAL = "official"
    GOVERNMENT = "government"
    PUBLIC_DATABASE = "public_database"
    COMPANY_DISCLOSURE = "company_disclosure"
    INDUSTRY_REPORT = "industry_report"
    MEDIA = "media"
    COMMUNITY = "community"
    ASSISTANT_BRIEF = "assistant_brief"
    USER_MATERIAL = "user_material"
    WEB = "web"


class SourceChannel(StrEnum):
    SEARCH = "search"
    RELIABLE_PROVIDER = "reliable_provider"
    USER_UPLOAD = "user_upload"
    ASSISTANT_BRIEF = "assistant_brief"
    MANUAL_LINK = "manual_link"
    SYSTEM = "system"


class SourceQuality(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ClaimStrength(StrEnum):
    FACT = "fact"
    ESTIMATE = "estimate"
    OPINION = "opinion"
    PREDICTION = "prediction"
    MARKETING = "marketing"


class ClaimType(StrEnum):
    MARKET_SIZE = "market_size"
    GROWTH_TREND = "growth_trend"
    PLAYER_STATUS = "player_status"
    TRANSACTION_UNIT = "transaction_unit"
    PRICING = "pricing"
    POLICY_RISK = "policy_risk"
    OPPORTUNITY = "opportunity"
    CONTENT_PATTERN = "content_pattern"
    GENERAL_FACT = "general_fact"


class EvidenceClaim(BaseModel):
    claim_id: str
    text: str
    claim_type: ClaimType = ClaimType.GENERAL_FACT
    support_level: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_verification: bool = True
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    evidence_ids: list[str] = Field(default_factory=list)
    counterevidence_ids: list[str] = Field(default_factory=list)
    notes: str | None = None


class EvidenceItem(BaseModel):
    id: str
    project_id: str
    source_title: str
    snippet: str
    source_url: str | None = None
    source_type: str | None = None
    source_channel: SourceChannel = SourceChannel.SEARCH
    source_policy: str | None = None
    raw_excerpt: str | None = None
    summary: str | None = None
    extraction_provider: str | None = None
    extraction_metadata: dict[str, Any] = Field(default_factory=dict)
    collection_metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_at: datetime | None = None
    claims: list[EvidenceClaim] = Field(default_factory=list)
    source_quality: SourceQuality = SourceQuality.UNKNOWN
    claim_strength: ClaimStrength = ClaimStrength.OPINION
    bias_risk: str | None = None
    recency: str | None = None
    corroborating_evidence_ids: list[str] = Field(default_factory=list)
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    needs_counterevidence: bool = False
    collected_by: str | None = None
    used_by_artifact_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    verification_status: VerificationStatus

    @model_validator(mode="after")
    def verified_evidence_requires_source_url(self) -> "EvidenceItem":
        if self.verification_status == VerificationStatus.VERIFIED and not self.source_url:
            raise ValueError("verified evidence requires source_url")
        return self
