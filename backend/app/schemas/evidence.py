"""Evidence schemas."""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"


class EvidenceItem(BaseModel):
    id: str
    project_id: str
    source_title: str
    snippet: str
    source_url: str | None = None
    source_type: str | None = None
    summary: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    verification_status: VerificationStatus

    @model_validator(mode="after")
    def verified_evidence_requires_source_url(self) -> "EvidenceItem":
        if self.verification_status == VerificationStatus.VERIFIED and not self.source_url:
            raise ValueError("verified evidence requires source_url")
        return self
