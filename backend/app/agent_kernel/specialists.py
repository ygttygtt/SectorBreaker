"""Typed task-scoped specialist Agents used by the V3 Master Agent."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SpecialistRole(StrEnum):
    VAULT_AUDITOR = "vault_auditor"
    RESEARCHER = "researcher"
    VERIFIER = "verifier"
    KNOWLEDGE_EDITOR = "knowledge_editor"


class SpecialistTask(BaseModel):
    role: SpecialistRole
    objective: str
    target_paths: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class SpecialistFinding(BaseModel):
    finding_type: str
    summary: str
    target_paths: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    requires_verification: bool = True


class SpecialistToolRecommendation(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class SpecialistChangeSuggestion(BaseModel):
    path: str
    after_content: str
    evidence_ids: list[str] = Field(default_factory=list)
    factual_change: bool = False


_ROLE_TOOL_ALLOWLISTS: dict[SpecialistRole, set[str]] = {
    SpecialistRole.VAULT_AUDITOR: {
        "inspect_vault_health",
        "inspect_maintenance_backlog",
        "retrieve_project_memory",
    },
    SpecialistRole.RESEARCHER: {"retrieve_project_memory", "search_web"},
    SpecialistRole.VERIFIER: {"retrieve_project_memory", "search_web"},
    SpecialistRole.KNOWLEDGE_EDITOR: {"retrieve_project_memory", "propose_change_set"},
}


class SpecialistResult(BaseModel):
    role: SpecialistRole
    objective: str
    summary: str
    findings: list[SpecialistFinding] = Field(default_factory=list)
    recommended_tool_calls: list[SpecialistToolRecommendation] = Field(default_factory=list)
    proposed_change: SpecialistChangeSuggestion | None = None
    stop_reason: str = ""

    @model_validator(mode="after")
    def enforce_role_boundary(self) -> "SpecialistResult":
        allowed = _ROLE_TOOL_ALLOWLISTS[self.role]
        denied = [item.tool_name for item in self.recommended_tool_calls if item.tool_name not in allowed]
        if denied:
            raise ValueError(
                f"{self.role.value} recommended disallowed tools: {', '.join(sorted(set(denied)))}"
            )
        if self.proposed_change is not None and self.role != SpecialistRole.KNOWLEDGE_EDITOR:
            raise ValueError("only knowledge_editor may return a proposed_change")
        return self
