"""Typed contracts for the demo-first Agent Contract Network."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field, model_validator

from backend.app.schemas.projects import SourcePolicy


class OrchestrationMode(StrEnum):
    ADAPTIVE_MULTI_AGENT = "adaptive_multi_agent"
    MASTER_ONLY = "master_only"


class ChallengeOutputType(StrEnum):
    STARTER_NOTE = "starter_note"


class PublishPolicy(StrEnum):
    PROPOSE_BEFORE_PUBLISH = "propose_before_publish"


class AgentTransport(StrEnum):
    LOCAL = "local"
    A2A = "a2a"


class WorkOrderType(StrEnum):
    RESEARCH = "research"
    VERIFY = "verify"
    EDIT = "edit"


class WorkOrderStatus(StrEnum):
    PLANNED = "planned"
    OFFERED = "offered"
    ASSIGNED = "assigned"
    RUNNING = "running"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REWORK = "rework"
    FAILED = "failed"
    BLOCKED = "blocked"


class MissionStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    WAITING_FOR_REVIEW = "waiting_for_review"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class ClaimCheckStatus(StrEnum):
    SUPPORTED = "supported"
    CONFLICTING = "conflicting"
    INSUFFICIENT = "insufficient"


class LiveChallengeRequest(BaseModel):
    domain: str = Field(min_length=1, max_length=200)
    question: str | None = Field(default=None, max_length=1000)
    deadline_seconds: int = Field(default=300, ge=180, le=600)
    output_type: ChallengeOutputType = ChallengeOutputType.STARTER_NOTE
    orchestration_mode: OrchestrationMode = OrchestrationMode.ADAPTIVE_MULTI_AGENT
    source_policy: SourcePolicy = SourcePolicy.RELIABLE_FIRST
    publish_policy: PublishPolicy = PublishPolicy.PROPOSE_BEFORE_PUBLISH


class AgentPerformance(BaseModel):
    assigned_tasks: int = 0
    accepted_tasks: int = 0
    rejected_tasks: int = 0
    rework_count: int = 0
    evidence_gain_total: int = 0
    average_latency_ms: float = 0.0
    average_duplicate_ratio: float = 0.0
    capability_reliability: dict[str, float] = Field(default_factory=dict)

    def reliability_for(self, capability: str) -> float:
        return min(1.0, max(0.0, self.capability_reliability.get(capability, 0.5)))


class AgentManifest(BaseModel):
    agent_id: str
    version: str = "1.0"
    display_name: str
    role: str
    capabilities: list[str]
    tool_allowlist: list[str]
    input_schema: str = "WorkOrder"
    output_schema: str = "AgentDeliverable"
    concurrency_limit: int = Field(default=1, ge=1, le=4)
    cost_tier: int = Field(default=1, ge=1, le=3)
    transport: AgentTransport = AgentTransport.LOCAL
    endpoint: str | None = None
    protocol_version: str | None = None
    available: bool = True
    performance: AgentPerformance = Field(default_factory=AgentPerformance)


class TaskBudget(BaseModel):
    max_steps: int = Field(default=3, ge=1, le=3)
    max_search_calls: int = Field(default=1, ge=0, le=3)
    max_provider_requests: int = Field(default=4, ge=0, le=12)
    max_extraction_requests: int = Field(default=3, ge=0, le=6)
    max_llm_calls: int = Field(default=3, ge=1, le=6)
    deadline_seconds: int = Field(default=120, ge=15, le=300)


class AgentBid(BaseModel):
    agent_id: str
    eligible: bool
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    capability_match: float = Field(default=0.0, ge=0.0, le=1.0)
    reliability: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_gain: float = Field(default=0.0, ge=0.0, le=1.0)
    budget_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    exclusion_reasons: list[str] = Field(default_factory=list)
    rationale: str = ""


class WorkOrder(BaseModel):
    id: str = Field(default_factory=lambda: f"WO-{uuid4().hex[:12]}")
    mission_id: str
    task_type: WorkOrderType
    objective: str
    research_angle: str = ""
    required_capabilities: list[str]
    depends_on: list[str] = Field(default_factory=list)
    context_refs: list[str] = Field(default_factory=list)
    expected_output_schema: str = "AgentDeliverable"
    acceptance_criteria: list[str] = Field(default_factory=list)
    budget: TaskBudget = Field(default_factory=TaskBudget)
    optional: bool = False
    status: WorkOrderStatus = WorkOrderStatus.PLANNED
    assigned_agent_id: str | None = None
    assignment_trace: list[AgentBid] = Field(default_factory=list)
    attempts: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ToolObservationRecord(BaseModel):
    tool_name: str
    success: bool
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None


class DeliverableFinding(BaseModel):
    summary: str = Field(validation_alias=AliasChoices("summary", "finding", "claim"))
    evidence_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("evidence_ids", "evidence_refs", "supporting_evidence"),
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    requires_verification: bool = True


class ClaimCheck(BaseModel):
    claim: str = Field(validation_alias=AliasChoices("claim", "claim_text", "statement"))
    status: ClaimCheckStatus
    evidence_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("evidence_ids", "evidence_refs", "supporting_evidence"),
    )
    reason: str = Field(default="", validation_alias=AliasChoices("reason", "reasoning", "assessment"))


class DeliverableUsage(BaseModel):
    steps: int = 0
    search_calls: int = 0
    provider_requests: int = 0
    extraction_requests: int = 0
    llm_calls: int = 0


class EvidenceCandidate(BaseModel):
    """Evidence returned by an opaque remote Agent before local admission."""

    candidate_id: str
    title: str
    url: str
    snippet: str = ""
    raw_excerpt: str = ""
    extraction_provider: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class AgentDeliverable(BaseModel):
    task_id: str
    mission_id: str
    agent_id: str
    summary: str
    findings: list[DeliverableFinding] = Field(default_factory=list)
    claim_checks: list[ClaimCheck] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_candidates: list[EvidenceCandidate] = Field(default_factory=list)
    observations: list[ToolObservationRecord] = Field(default_factory=list)
    draft_markdown: str | None = None
    proposed_path: str | None = None
    usage: DeliverableUsage = Field(default_factory=DeliverableUsage)
    latency_ms: int = 0
    output_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def verify_output_hash(self) -> "AgentDeliverable":
        # latency_ms is local settlement metadata, not part of the submitted
        # artifact.  Every other field is protected so a remote Artifact cannot
        # be altered in transit and still pass local admission.
        payload = self.model_dump_json(exclude={"output_hash", "latency_ms"})
        expected = "sha256:" + sha256(payload.encode("utf-8")).hexdigest()
        if self.output_hash and self.output_hash != expected:
            raise ValueError("AgentDeliverable output_hash mismatch")
        self.output_hash = expected
        return self


class TaskSettlement(BaseModel):
    task_id: str
    agent_id: str
    accepted: bool
    quality_score: float = Field(ge=0.0, le=1.0)
    evidence_gain: int = Field(default=0, ge=0)
    duplicate_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    budget_efficiency: float = Field(default=0.0, ge=0.0, le=1.0)
    rework_count: int = Field(default=0, ge=0)
    reliability_before: float = Field(default=0.5, ge=0.0, le=1.0)
    reliability_after: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentMission(BaseModel):
    id: str = Field(default_factory=lambda: f"MISSION-{uuid4().hex[:12]}")
    run_id: str
    project_id: str
    domain: str
    objective: str
    deadline_seconds: int = Field(default=300, ge=180, le=600)
    status: MissionStatus = MissionStatus.PLANNED
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deadline_at: datetime
    work_orders: list[WorkOrder]
    deliverables: list[AgentDeliverable] = Field(default_factory=list)
    settlements: list[TaskSettlement] = Field(default_factory=list)
    change_set_id: str | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    failure_reason: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_dag(self) -> "AgentMission":
        if not self.work_orders or len(self.work_orders) > 6:
            raise ValueError("mission requires 1-6 work orders")
        ids = [item.id for item in self.work_orders]
        if len(ids) != len(set(ids)):
            raise ValueError("work order ids must be unique")
        known = set(ids)
        for item in self.work_orders:
            if item.mission_id != self.id:
                raise ValueError("work order mission_id mismatch")
            if set(item.depends_on) - known:
                raise ValueError("work order references unknown dependency")
            if item.id in item.depends_on:
                raise ValueError("work order cannot depend on itself")
            if item.task_type == WorkOrderType.EDIT and not item.depends_on:
                raise ValueError("editor work order requires accepted upstream evidence")
        visiting: set[str] = set()
        visited: set[str] = set()
        graph = {item.id: item.depends_on for item in self.work_orders}

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("mission work order graph must be acyclic")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in graph[node_id]:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for work_order_id in ids:
            visit(work_order_id)
        return self


class ReadinessCheck(BaseModel):
    key: str
    label: str
    ready: bool
    critical: bool = True
    detail: str
    action: str | None = None


class DemoReadiness(BaseModel):
    ready: bool
    checks: list[ReadinessCheck]
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    live_only: bool = True
