"""ChangeSet proposal, approval, application, and rollback."""

from __future__ import annotations

from datetime import UTC, datetime
from difflib import unified_diff
from pathlib import Path
from uuid import uuid4

from backend.app.agent_state.models import AutonomyPolicy
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ChangeOperation,
    ChangeOperationType,
    ChangeSet,
    ChangeSetProposalRequest,
    ChangeSetStatus,
    MaintenanceTaskStatus,
)
from backend.app.storage.sqlite import SQLiteRepository


class ChangeSetService:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def propose(
        self,
        project_id: str,
        request: ChangeSetProposalRequest,
        *,
        actor: str = "master_agent",
        run_id: str | None = None,
    ) -> ChangeSet:
        active = self._active_by_path(project_id).get(_safe_path(request.path))
        operation_type = ChangeOperationType.UPDATE if active else ChangeOperationType.CREATE
        before_content = active.content if active else ""
        if before_content == request.after_content:
            raise ValueError("proposed content is identical to the active revision")
        operation = ChangeOperation(
            operation=operation_type,
            path=_safe_path(request.path),
            base_hash=active.content_hash if active else "",
            before_content=before_content,
            after_content=request.after_content,
            unified_diff="".join(unified_diff(
                before_content.splitlines(keepends=True),
                request.after_content.splitlines(keepends=True),
                fromfile=f"a/{request.path}",
                tofile=f"b/{request.path}",
            )),
            factual_change=request.factual_change,
        )
        change_set = ChangeSet(
            id=f"CS-{uuid4().hex[:12]}",
            project_id=project_id,
            origin_run_id=run_id,
            task_id=request.task_id,
            summary=request.summary,
            evidence_ids=request.evidence_ids,
            operations=[operation],
            created_by_agent=actor,
        )
        self.repository.save_change_set(change_set)
        return change_set

    def approve(self, change_set_id: str) -> ChangeSet:
        change_set = self.repository.get_change_set(change_set_id)
        if change_set.status != ChangeSetStatus.PROPOSED:
            raise ValueError(f"change set is not proposed: {change_set.status.value}")
        change_set.status = ChangeSetStatus.APPROVED
        change_set.approved_at = datetime.now(UTC)
        self.repository.save_change_set(change_set)
        return change_set

    def apply(self, change_set_id: str, *, policy: AutonomyPolicy | None = None) -> ChangeSet:
        change_set = self.repository.get_change_set(change_set_id)
        policy = policy or AutonomyPolicy()
        if change_set.status != ChangeSetStatus.APPROVED:
            raise ValueError("change set requires explicit approval before apply")
        if len(change_set.operations) > policy.max_files_per_run:
            return self._deny(change_set, "change set exceeds max_files_per_run")
        changed_bytes = sum(len(item.after_content.encode("utf-8")) for item in change_set.operations)
        if changed_bytes > policy.max_changed_bytes:
            return self._deny(change_set, "change set exceeds max_changed_bytes")
        if any(item.factual_change for item in change_set.operations) and policy.require_evidence_for_fact_change:
            if not change_set.evidence_ids:
                return self._deny(change_set, "factual changes require evidence ids")

        active_by_path = self._active_by_path(change_set.project_id)
        operation_paths = [item.path for item in change_set.operations]
        if len(operation_paths) != len(set(operation_paths)):
            return self._deny(change_set, "change set contains duplicate target paths")

        # Validate the entire journal before writing any revision. A later
        # conflict must never leave an earlier operation partially applied.
        predecessors: dict[str, Artifact | None] = {}
        for operation in change_set.operations:
            current = active_by_path.get(operation.path)
            if operation.operation == ChangeOperationType.CREATE:
                if current is not None:
                    return self._conflict(change_set, f"path already exists: {operation.path}")
                if not policy.allow_create:
                    return self._deny(change_set, "autonomy policy denies create")
                predecessors[operation.path] = None
                continue
            if current is None:
                return self._conflict(change_set, f"active path is missing: {operation.path}")
            if current.content_hash != operation.base_hash:
                return self._conflict(change_set, f"base hash changed: {operation.path}")
            predecessors[operation.path] = current

        applied_ids: list[str] = []
        for operation in change_set.operations:
            artifact = self._artifact_from_operation(
                change_set,
                operation,
                predecessor=predecessors[operation.path],
            )
            self.repository.add_artifact(artifact)
            applied_ids.append(artifact.id)

        change_set.status = ChangeSetStatus.APPLIED
        change_set.applied_at = datetime.now(UTC)
        change_set.applied_artifact_ids = applied_ids
        self.repository.save_change_set(change_set)
        if change_set.task_id:
            for task in self.repository.list_maintenance_tasks(change_set.project_id):
                if task.id == change_set.task_id:
                    task.status = MaintenanceTaskStatus.DONE
                    task.change_set_id = change_set.id
                    self.repository.save_maintenance_task(task)
                    break
        return change_set

    def rollback(self, change_set_id: str) -> ChangeSet:
        change_set = self.repository.get_change_set(change_set_id)
        if change_set.status != ChangeSetStatus.APPLIED:
            raise ValueError("only applied change sets can be rolled back")
        if len(change_set.applied_artifact_ids) != len(change_set.operations):
            raise ValueError("change set artifact journal is incomplete")

        active_by_path = self._active_by_path(change_set.project_id)
        rollback_ids: list[str] = []
        for operation, applied_id in zip(change_set.operations, change_set.applied_artifact_ids, strict=True):
            current = active_by_path.get(operation.path)
            if current is None or current.id != applied_id:
                return self._conflict(change_set, f"active revision changed after apply: {operation.path}")
            if operation.operation == ChangeOperationType.CREATE:
                self.repository.set_artifact_active(current.id, False)
                rollback_ids.append(current.id)
                continue
            predecessor = self.repository.get_artifact(current.supersedes) if current.supersedes else None
            rollback_artifact = Artifact(
                id=f"ART-ROLLBACK-{uuid4().hex[:12]}",
                project_id=change_set.project_id,
                artifact_type=current.artifact_type,
                title=current.title,
                content_path=current.content_path,
                content=operation.before_content,
                source_evidence_ids=(
                    predecessor.source_evidence_ids if predecessor is not None else current.source_evidence_ids
                ),
                schema_version="v3-knowledge-ops",
                supersedes=current.id,
                change_set_id=change_set.id,
            )
            self.repository.add_artifact(rollback_artifact)
            rollback_ids.append(rollback_artifact.id)

        change_set.status = ChangeSetStatus.ROLLED_BACK
        change_set.rolled_back_at = datetime.now(UTC)
        change_set.rollback_artifact_ids = rollback_ids
        self.repository.save_change_set(change_set)
        return change_set

    def _active_by_path(self, project_id: str) -> dict[str, Artifact]:
        return {item.content_path: item for item in self.repository.list_artifacts(project_id)}

    @staticmethod
    def _artifact_from_operation(
        change_set: ChangeSet,
        operation: ChangeOperation,
        predecessor: Artifact | None,
    ) -> Artifact:
        title = predecessor.title if predecessor else Path(operation.path).stem
        return Artifact(
            id=f"ART-CHANGE-{uuid4().hex[:12]}",
            project_id=change_set.project_id,
            artifact_type=predecessor.artifact_type if predecessor else ArtifactType.VAULT_NOTE,
            title=title,
            content_path=operation.path,
            content=operation.after_content,
            source_evidence_ids=change_set.evidence_ids,
            schema_version="v3-knowledge-ops",
            supersedes=predecessor.id if predecessor else None,
            change_set_id=change_set.id,
            run_id=change_set.origin_run_id,
        )

    def _conflict(self, change_set: ChangeSet, message: str) -> ChangeSet:
        change_set.status = ChangeSetStatus.CONFLICTED
        change_set.error = message
        self.repository.save_change_set(change_set)
        return change_set

    def _deny(self, change_set: ChangeSet, message: str) -> ChangeSet:
        change_set.status = ChangeSetStatus.DENIED
        change_set.error = message
        self.repository.save_change_set(change_set)
        return change_set


def _safe_path(value: str) -> str:
    return ChangeOperation(
        operation=ChangeOperationType.CREATE,
        path=value,
        after_content="# validation",
    ).path
