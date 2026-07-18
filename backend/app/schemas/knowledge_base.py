"""Public contracts for V3 autonomous knowledge-base management."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class VaultImportRequest(BaseModel):
    source_path: str = Field(min_length=1)
    max_files: int = Field(default=1000, ge=1, le=20_000)
    max_total_bytes: int = Field(default=50 * 1024 * 1024, ge=1024, le=1024 * 1024 * 1024)


class VaultImportRecord(BaseModel):
    id: str
    project_id: str
    source_path: str
    note_count: int = 0
    total_bytes: int = 0
    snapshot_hash: str
    imported_paths: list[str] = Field(default_factory=list)
    skipped_paths: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VaultNoteSummary(BaseModel):
    artifact_id: str
    relative_path: str
    title: str
    revision: int
    content_hash: str
    wikilinks: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class VaultStatus(BaseModel):
    project_id: str
    latest_import: VaultImportRecord | None = None
    active_note_count: int = 0
    notes: list[VaultNoteSummary] = Field(default_factory=list)


class HealthFindingType(StrEnum):
    BROKEN_LINK = "broken_link"
    ORPHAN_NOTE = "orphan_note"
    DUPLICATE_TITLE = "duplicate_title"
    MISSING_FRONTMATTER = "missing_frontmatter"
    MISSING_EVIDENCE_METADATA = "missing_evidence_metadata"
    UNRESOLVED_MARKER = "unresolved_marker"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class HealthFinding(BaseModel):
    id: str
    finding_type: HealthFindingType
    severity: FindingSeverity = FindingSeverity.WARNING
    target_paths: list[str] = Field(default_factory=list)
    explanation: str
    suggested_action: str
    detector: str = "deterministic_vault_scanner"
    auto_fixable: bool = False


class KnowledgeHealthReport(BaseModel):
    id: str
    project_id: str
    vault_import_id: str | None = None
    snapshot_hash: str
    metrics: dict[str, int] = Field(default_factory=dict)
    findings: list[HealthFinding] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MaintenanceTaskStatus(StrEnum):
    OPEN = "open"
    PLANNED = "planned"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    DISMISSED = "dismissed"


class MaintenanceTask(BaseModel):
    id: str
    project_id: str
    fingerprint: str
    finding_ids: list[str] = Field(default_factory=list)
    task_type: str
    objective: str
    target_paths: list[str] = Field(default_factory=list)
    priority: int = Field(default=3, ge=1, le=5)
    status: MaintenanceTaskStatus = MaintenanceTaskStatus.OPEN
    assigned_specialist: str | None = None
    required_evidence_types: list[str] = Field(default_factory=list)
    approval_required: bool = True
    change_set_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChangeSetStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    APPLIED = "applied"
    CONFLICTED = "conflicted"
    ROLLED_BACK = "rolled_back"
    DENIED = "denied"


class ChangeOperationType(StrEnum):
    CREATE = "create"
    UPDATE = "update"


class ChangeOperation(BaseModel):
    operation: ChangeOperationType
    path: str
    base_hash: str = ""
    before_content: str = ""
    after_content: str
    unified_diff: str = ""
    factual_change: bool = False

    @field_validator("path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip("/")
        if not normalized or normalized.startswith(".") or ".." in normalized.split("/"):
            raise ValueError("change path must be a safe relative path")
        if not normalized.lower().endswith(".md"):
            raise ValueError("only Markdown changes are supported")
        return normalized


class ChangeSet(BaseModel):
    id: str
    project_id: str
    task_id: str | None = None
    status: ChangeSetStatus = ChangeSetStatus.PROPOSED
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    operations: list[ChangeOperation]
    created_by_agent: str = "master_agent"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None
    applied_at: datetime | None = None
    rolled_back_at: datetime | None = None
    applied_artifact_ids: list[str] = Field(default_factory=list)
    rollback_artifact_ids: list[str] = Field(default_factory=list)
    error: str | None = None

    @model_validator(mode="after")
    def require_operations(self) -> "ChangeSet":
        if not self.operations:
            raise ValueError("change set requires at least one operation")
        return self


class ChangeSetProposalRequest(BaseModel):
    task_id: str | None = None
    summary: str = Field(min_length=1)
    path: str
    after_content: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    factual_change: bool = False


class MaintenanceRunRequest(BaseModel):
    objective: str = ""
    task_ids: list[str] = Field(default_factory=list)
    execution_mode: str = "plan_only"
    autonomy_policy: dict[str, Any] = Field(default_factory=dict)
