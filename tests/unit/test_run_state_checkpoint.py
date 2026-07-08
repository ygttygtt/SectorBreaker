"""Tests for run state checkpoint persistence."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agent_state.models import SectorBreakerState
from backend.app.storage.sqlite import SQLiteRepository, init_database


@pytest.fixture()
def repo(tmp_path: Path) -> SQLiteRepository:
    db = tmp_path / "test.db"
    init_database(db)
    return SQLiteRepository(db)


def _make_state(domain: str = "test-domain") -> SectorBreakerState:
    return SectorBreakerState.initialize(
        project_id="proj-test",
        domain=domain,
        user_goal="build knowledge base for " + domain,
    )


def test_save_and_load_checkpoint_roundtrip(repo: SQLiteRepository) -> None:
    state = _make_state()
    state.evidence_refs = ["EV-KERNEL-001", "EV-KERNEL-002"]

    repo.save_run_state_checkpoint(
        run_id="run-001",
        project_id="proj-test",
        state=state,
        checkpoint_type="artifact_write",
        artifact_id="ART-KERNEL-L1-abc123",
        iteration=3,
    )

    loaded = repo.load_run_state_checkpoint(run_id="run-001")
    assert loaded is not None
    assert loaded.evidence_refs == ["EV-KERNEL-001", "EV-KERNEL-002"]
    assert loaded.meta_context.domain == "test-domain"


def test_load_checkpoint_returns_none_when_no_checkpoint(repo: SQLiteRepository) -> None:
    result = repo.load_run_state_checkpoint(run_id="nonexistent-run")
    assert result is None


def test_save_multiple_checkpoints_load_returns_latest(repo: SQLiteRepository) -> None:
    state_v1 = _make_state()
    state_v1.evidence_refs = ["EV-001"]
    repo.save_run_state_checkpoint(
        run_id="run-002",
        project_id="proj-test",
        state=state_v1,
        checkpoint_type="artifact_write",
        artifact_id="ART-001",
        iteration=2,
    )

    state_v2 = _make_state()
    state_v2.evidence_refs = ["EV-001", "EV-002", "EV-003"]
    repo.save_run_state_checkpoint(
        run_id="run-002",
        project_id="proj-test",
        state=state_v2,
        checkpoint_type="artifact_write",
        artifact_id="ART-002",
        iteration=5,
    )

    loaded = repo.load_run_state_checkpoint(run_id="run-002")
    assert loaded is not None
    assert len(loaded.evidence_refs) == 3


def test_load_latest_resumable_project_checkpoint_uses_continue_run_state(repo: SQLiteRepository) -> None:
    initial_state = _make_state()
    initial_state.evidence_refs = ["EV-INITIAL"]
    repo.save_run_state_checkpoint(
        run_id="proj-test",
        project_id="proj-test",
        state=initial_state,
        checkpoint_type="run_end_completed",
        iteration=4,
    )

    continued_state = _make_state()
    continued_state.evidence_refs = ["EV-INITIAL", "EV-CONTINUE"]
    repo.save_run_state_checkpoint(
        run_id="run-continue-001",
        project_id="proj-test",
        state=continued_state,
        checkpoint_type="artifact_write",
        artifact_id="ART-CONTINUE",
        iteration=2,
    )

    loaded = repo.load_latest_resumable_project_checkpoint(project_id="proj-test")

    assert loaded is not None
    assert loaded.evidence_refs == ["EV-INITIAL", "EV-CONTINUE"]


def test_load_latest_resumable_project_checkpoint_ignores_failed_run_end(repo: SQLiteRepository) -> None:
    good_state = _make_state()
    good_state.evidence_refs = ["EV-GOOD"]
    repo.save_run_state_checkpoint(
        run_id="run-good",
        project_id="proj-test",
        state=good_state,
        checkpoint_type="artifact_write",
        artifact_id="ART-GOOD",
        iteration=3,
    )

    failed_state = _make_state()
    failed_state.evidence_refs = ["EV-FAILED"]
    repo.save_run_state_checkpoint(
        run_id="run-failed",
        project_id="proj-test",
        state=failed_state,
        checkpoint_type="run_end",
        iteration=9,
    )

    loaded = repo.load_latest_resumable_project_checkpoint(project_id="proj-test")

    assert loaded is not None
    assert loaded.evidence_refs == ["EV-GOOD"]
