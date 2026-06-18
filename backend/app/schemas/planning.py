"""Supervisor planning and workflow definition schemas."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentRunMode(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    DEGRADED = "degraded"
    SKIPPED = "skipped"


class VerificationLevel(StrEnum):
    NONE = "none"
    NORMAL = "normal"
    STRICT = "strict"
    ADVERSARIAL = "adversarial"


class WorkflowNodeStatus(StrEnum):
    PENDING = "pending"
    ENABLED = "enabled"
    SKIPPED = "skipped"
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"


class AgentTask(BaseModel):
    agent_id: str
    display_name: str
    role: str
    reason: str
    run_mode: AgentRunMode = AgentRunMode.REQUIRED
    execution_group: str
    depends_on: list[str] = Field(default_factory=list)
    source_scope: list[str] = Field(default_factory=list)
    output_contract: str
    verification_level: VerificationLevel = VerificationLevel.NORMAL
    fallback: str


class SkippedAgent(BaseModel):
    agent_id: str
    display_name: str
    reason: str


class VerificationPlan(BaseModel):
    key_claim_types: list[str] = Field(default_factory=list)
    counterevidence_triggers: list[str] = Field(default_factory=list)
    downgraded_source_types: list[str] = Field(default_factory=list)
    notes: str | None = None


class AgentSelectionSignal(BaseModel):
    signal: str
    matched: bool
    weight: int = 0
    reason: str


class AgentSelectionDecision(BaseModel):
    agent_id: str
    display_name: str
    enabled: bool
    score: int = 0
    rationale: list[str] = Field(default_factory=list)
    disqualifiers: list[str] = Field(default_factory=list)
    signals: list[AgentSelectionSignal] = Field(default_factory=list)
    source_scope: list[str] = Field(default_factory=list)


class SupervisorPlan(BaseModel):
    schema_version: str = "1"
    intent_summary: str
    source_policy: str
    source_policy_reason: str
    selected_agents: list[AgentTask]
    skipped_agents: list[SkippedAgent] = Field(default_factory=list)
    verification_plan: VerificationPlan = Field(default_factory=VerificationPlan)
    human_review_points: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    selection_trace: list[AgentSelectionDecision] = Field(default_factory=list)


class QAReport(BaseModel):
    passed: bool
    blocking_issues: list[str] = Field(default_factory=list)
    retry_tasks: list[str] = Field(default_factory=list)
    user_action_needed: list[str] = Field(default_factory=list)
    can_continue_with_warning: bool = False


class WorkflowNode(BaseModel):
    id: str
    label: str
    node_type: str
    agent_id: str | None = None
    group: str
    status: WorkflowNodeStatus = WorkflowNodeStatus.PENDING
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None


class WorkflowDefinition(BaseModel):
    schema_version: str = "1"
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
