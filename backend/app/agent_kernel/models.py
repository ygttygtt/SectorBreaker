"""Typed contracts for the V2 Agent Kernel."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from backend.app.agent_state.models import (
    EntityRecord,
    KnowledgeClaim,
    OpenQuestion,
    RelationshipRecord,
    SourceMemory,
)


class AgentActionType(StrEnum):
    CALL_TOOL = "call_tool"
    UPDATE_STATE = "update_state"
    WRITE_ARTIFACT = "write_artifact"
    REVIEW_ARTIFACT = "review_artifact"
    ASK_USER = "ask_user"
    FINISH = "finish"
    BLOCK = "block"


class KernelRunStatus(StrEnum):
    COMPLETED = "completed"
    WAITING_FOR_HUMAN = "waiting_for_human"
    BLOCKED = "blocked"
    FAILED = "failed"
    MAX_ITERATIONS = "max_iterations"


class TraceEventKind(StrEnum):
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    STATE_UPDATE = "state_update"
    DECISION = "decision"
    WARNING = "warning"
    BLOCKED = "blocked"


class ToolCall(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ToolSpec(BaseModel):
    name: str
    description: str
    args_schema: dict[str, Any] = Field(default_factory=dict)


class KernelStateDelta(BaseModel):
    source_memories: list[SourceMemory] = Field(default_factory=list)
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    updated_claims: list[KnowledgeClaim] = Field(default_factory=list)
    entities: list[EntityRecord] = Field(default_factory=list)
    relationships: list[RelationshipRecord] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    task_notes: list[str] = Field(default_factory=list)
    rejected_notes: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    coverage_updates: list[dict[str, Any]] = Field(default_factory=list)
    hidden_source_ids: list[str] = Field(default_factory=list)
    deleted_source_ids: list[str] = Field(default_factory=list)
    hidden_claim_ids: list[str] = Field(default_factory=list)
    deleted_claim_ids: list[str] = Field(default_factory=list)
    superseded_claim_ids: list[str] = Field(default_factory=list)
    resolved_open_question_ids: list[str] = Field(default_factory=list)
    phase_reflection: str = ""

    def is_empty(self) -> bool:
        return not (
            self.source_memories
            or self.claims
            or self.updated_claims
            or self.entities
            or self.relationships
            or self.open_questions
            or self.evidence_ids
            or self.artifact_ids
            or self.task_notes
            or self.rejected_notes
            or self.coverage_gaps
            or self.coverage_updates
            or self.hidden_source_ids
            or self.deleted_source_ids
            or self.hidden_claim_ids
            or self.deleted_claim_ids
            or self.superseded_claim_ids
            or self.resolved_open_question_ids
            or self.phase_reflection
        )


class AgentDecision(BaseModel):
    thought_summary: str
    action_type: AgentActionType
    tool_call: ToolCall | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    state_delta: KernelStateDelta | None = None
    expected_observation: str = ""
    stop_reason: str = ""
    current_goal: str = ""
    plan_steps: list[str] = Field(default_factory=list)
    progress_check: str = ""

    @model_validator(mode="after")
    def validate_action_payload(self) -> "AgentDecision":
        if self.action_type in {
            AgentActionType.CALL_TOOL,
            AgentActionType.WRITE_ARTIFACT,
            AgentActionType.REVIEW_ARTIFACT,
            AgentActionType.ASK_USER,
        } and self.tool_call is None and not self.tool_calls:
            raise ValueError(f"{self.action_type.value} requires tool_call")
        if self.action_type in {AgentActionType.FINISH, AgentActionType.BLOCK} and not self.stop_reason:
            raise ValueError(f"{self.action_type.value} requires stop_reason")
        return self


class KernelObservation(BaseModel):
    tool_name: str
    success: bool
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    state_delta: KernelStateDelta = Field(default_factory=KernelStateDelta)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    requires_human: bool = False
    error: str | None = None


class KernelTraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"KTE-{uuid4().hex[:12]}")
    kind: TraceEventKind
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KernelLoopConfig(BaseModel):
    max_iterations: int = Field(default=36, ge=1)
    max_search_calls: int = Field(default=16, ge=0)
    max_writer_calls: int = Field(default=16, ge=0)
    max_consecutive_failed_tools: int = Field(default=3, ge=1)


class KernelRunResult(BaseModel):
    status: KernelRunStatus
    state_version: str
    trace: list[KernelTraceEvent] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    stop_reason: str = ""
    iterations: int = 0
