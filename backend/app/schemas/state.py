"""LangGraph state schemas."""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from backend.app.schemas.artifacts import Artifact
from backend.app.schemas.evidence import EvidenceItem


class ResearchGate(StrEnum):
    SCOPE = "scope"
    RESEARCH_FRAME = "research_frame"
    EVIDENCE = "evidence"
    KNOWLEDGE_MAP = "knowledge_map"
    OPPORTUNITY = "opportunity"
    EXPORT = "export"


class ResearchState(BaseModel):
    project_id: str
    current_gate: ResearchGate
    graph_state_version: str = "1"
    evidence: list[EvidenceItem] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    coverage_checklist: dict[str, bool] = Field(default_factory=dict)
    qa_issues: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def export_gate_requires_supported_artifacts(self) -> "ResearchState":
        if self.current_gate != ResearchGate.EXPORT:
            return self
        unsupported = [artifact.id for artifact in self.artifacts if not artifact.source_evidence_ids]
        if unsupported:
            raise ValueError(f"export artifacts require source evidence: {unsupported}")
        return self
