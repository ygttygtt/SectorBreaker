"""Run and event schemas for async workflow execution."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"
    FAILED = "failed"


class RunEvent(BaseModel):
    event_type: str  # gate_start | step_start | step_complete | artifact_created | evidence_collected | gate_complete | waiting_for_human | error
    gate: str
    step: str | None = None
    agent: str | None = None
    message: str
    data: dict[str, Any] | None = None
    timestamp: float = Field(default_factory=lambda: datetime.now(UTC).timestamp())


class ResearchRun(BaseModel):
    id: str
    project_id: str
    status: RunStatus = RunStatus.PENDING
    current_gate: str | None = None
    current_step: str | None = None
    workflow_state: str | None = None  # JSON-serialized workflow state for pause/resume
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class UserInput(BaseModel):
    id: str
    run_id: str
    gate: str
    input_type: str  # note | guidance | evidence_data
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResumeRequest(BaseModel):
    """User confirms a gate review, optionally providing supplementary information."""
    guidance: str | None = None  # free-text direction for next steps
    evidence_data: str | None = None  # structured data to inject as evidence
