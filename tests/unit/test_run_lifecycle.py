from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.app.agent_state.models import SectorBreakerState
from backend.app.agent_kernel.models import KernelRunResult, KernelRunStatus
from backend.app.api.app import _finalize_kernel_run
from backend.app.schemas import RunEvent, RunStatus
from backend.app.storage.sqlite import SQLiteRepository, init_database


def _repository(tmp_path: Path) -> SQLiteRepository:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    return SQLiteRepository(database_path)


def _expire_run(repository: SQLiteRepository, run_id: str) -> None:
    with repository._connect() as connection:  # noqa: SLF001 - focused storage contract test
        connection.execute(
            "UPDATE runs SET lease_expires_at = ? WHERE id = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), run_id),
        )


def test_run_lease_migrations_are_complete_and_restart_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    init_database(database_path)
    init_database(database_path)
    repository = SQLiteRepository(database_path)
    with repository._connect() as connection:  # noqa: SLF001 - schema contract test
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(runs)").fetchall()}
        indexes = {row["name"] for row in connection.execute("PRAGMA index_list(runs)").fetchall()}

    assert {
        "heartbeat_at",
        "lease_owner_id",
        "lease_expires_at",
        "terminal_reason",
        "resumed_from_run_id",
    }.issubset(columns)
    assert "idx_runs_single_recovery_child" in indexes


def test_reconcile_only_expired_leases_and_requires_checkpoint_for_recovery(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    recoverable = repository.create_claimed_run(
        "project-recoverable",
        lease_owner_id="worker-a",
        lease_seconds=60,
    )
    assert repository.reconcile_stale_runs() == []

    repository.save_run_state_checkpoint(
        run_id=recoverable.id,
        project_id=recoverable.project_id,
        state=SectorBreakerState.initialize(
            project_id=recoverable.project_id,
            domain="test",
            user_goal="test",
        ),
        checkpoint_type="run_end",
    )
    _expire_run(repository, recoverable.id)
    [interrupted] = repository.reconcile_stale_runs()
    assert interrupted.status == RunStatus.INTERRUPTED
    assert interrupted.terminal_reason == "lease_expired"

    orphaned = repository.create_claimed_run(
        "project-orphaned",
        lease_owner_id="worker-b",
        lease_seconds=60,
    )
    _expire_run(repository, orphaned.id)
    [failed] = repository.reconcile_stale_runs()
    assert failed.status == RunStatus.FAILED
    assert failed.terminal_reason == "orphaned_no_checkpoint"


def test_waiting_run_is_not_reconciled_and_resume_claim_is_compare_and_set(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    run = repository.create_claimed_run(
        "project-waiting",
        lease_owner_id="worker-a",
        lease_seconds=60,
    )
    repository.finish_owned_run(
        run.id,
        lease_owner_id="worker-a",
        status=RunStatus.WAITING_FOR_HUMAN,
        current_gate="human_feedback",
        terminal_reason="need confirmation",
    )

    assert repository.reconcile_stale_runs(datetime.now(UTC) + timedelta(days=1)) == []
    assert repository.claim_waiting_run(
        run.id,
        lease_owner_id="worker-b",
        lease_seconds=60,
    ) is True
    assert repository.claim_waiting_run(
        run.id,
        lease_owner_id="worker-c",
        lease_seconds=60,
    ) is False


def test_waiting_finalization_persists_typed_event_before_releasing_lease(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    run = repository.create_claimed_run(
        "project-human",
        lease_owner_id="worker-a",
        lease_seconds=60,
    )
    repository.save_run_state_checkpoint(
        run_id=run.id,
        project_id=run.project_id,
        state=SectorBreakerState.initialize(
            project_id=run.project_id,
            domain="test",
            user_goal="test",
        ),
        checkpoint_type="run_end",
    )

    _finalize_kernel_run(
        repository,
        run.id,
        KernelRunResult(
            status=KernelRunStatus.WAITING_FOR_HUMAN,
            state_version="3",
            stop_reason="请确认范围",
        ),
        lease_owner_id="worker-a",
    )

    finalized = repository.get_run(run.id)
    assert finalized.status == RunStatus.WAITING_FOR_HUMAN
    assert finalized.lease_owner_id is None
    [event] = repository.list_run_events(run.id)
    assert event.event_type == "waiting_for_human"
    assert event.data and event.data["checkpoint_available"] is True


def test_old_worker_cannot_append_or_finalize_after_losing_lease(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    run = repository.create_claimed_run(
        "project-owned",
        lease_owner_id="worker-current",
        lease_seconds=60,
    )

    with pytest.raises(RuntimeError, match="lease lost"):
        repository.add_run_event(
            RunEvent(event_type="node_progress", gate="agent_decide", message="stale"),
            run.id,
            lease_owner_id="worker-stale",
        )
    with pytest.raises(RuntimeError, match="lease lost"):
        repository.finish_owned_run(
            run.id,
            lease_owner_id="worker-stale",
            status=RunStatus.COMPLETED,
            current_gate="completed",
        )

    assert repository.list_run_events(run.id) == []
    assert repository.get_run(run.id).status == RunStatus.RUNNING

    _expire_run(repository, run.id)
    with pytest.raises(RuntimeError, match="lease lost"):
        repository.add_run_event(
            RunEvent(event_type="node_progress", gate="agent_decide", message="expired"),
            run.id,
            lease_owner_id="worker-current",
        )


def test_only_one_recovery_child_can_be_created(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    first = repository.create_claimed_run(
        "project-lineage",
        lease_owner_id="worker-first",
        lease_seconds=60,
        resumed_from_run_id="run-parent",
    )
    repository.finish_owned_run(
        first.id,
        lease_owner_id="worker-first",
        status=RunStatus.COMPLETED,
        current_gate="completed",
    )

    with pytest.raises(ValueError, match="recovery already exists"):
        repository.create_claimed_run(
            "project-lineage",
            lease_owner_id="worker-second",
            lease_seconds=60,
            resumed_from_run_id="run-parent",
        )
