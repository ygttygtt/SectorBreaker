import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.agent_network.planner import MissionPlanDraft
from backend.app.agent_network.registry import AgentRegistry
from backend.app.agent_network.scheduler import AgentScheduler
from backend.app.providers.failover import FailoverContentExtractionProvider, FailoverLLMProvider
from backend.app.providers.interfaces import ExtractedPage
from backend.app.schemas import (
    AgentDeliverable,
    AgentManifest,
    AgentMission,
    AgentPerformance,
    AgentTransport,
    WorkOrder,
    WorkOrderType,
)


def _work_order(**updates):
    values = {
        "id": "WO-1",
        "mission_id": "MISSION-1",
        "task_type": WorkOrderType.RESEARCH,
        "objective": "研究产业生态",
        "required_capabilities": ["research_ecosystem"],
    }
    values.update(updates)
    return WorkOrder(**values)


def test_scheduler_hard_filters_unavailable_a2a_and_explains_local_award():
    remote = AgentManifest(
        agent_id="remote",
        display_name="Remote",
        role="researcher",
        capabilities=["research_ecosystem"],
        tool_allowlist=["search_web"],
        transport=AgentTransport.A2A,
        available=False,
        performance=AgentPerformance(accepted_tasks=9, evidence_gain_total=30),
    )
    local = AgentManifest(
        agent_id="local",
        display_name="Local",
        role="researcher",
        capabilities=["research_ecosystem"],
        tool_allowlist=["search_web"],
        available=True,
    )
    task = _work_order()
    winner = AgentScheduler(AgentRegistry([remote, local])).assign(task, remaining_seconds=200)
    assert winner.agent_id == "local"
    remote_bid = next(item for item in task.assignment_trace if item.agent_id == "remote")
    assert not remote_bid.eligible
    assert "transport unavailable" in remote_bid.exclusion_reasons
    assert task.assignment_trace[0].rationale.startswith("capability=")


def test_scheduler_score_rewards_capability_reliability_evidence_and_latency():
    high = AgentManifest(
        agent_id="high",
        display_name="High",
        role="researcher",
        capabilities=["research_ecosystem"],
        tool_allowlist=["search_web"],
        performance=AgentPerformance(
            accepted_tasks=10,
            evidence_gain_total=30,
            average_latency_ms=10_000,
            capability_reliability={"research_ecosystem": 0.9},
        ),
    )
    low = AgentManifest(
        agent_id="low",
        display_name="Low",
        role="researcher",
        capabilities=["research_ecosystem"],
        tool_allowlist=["search_web"],
        cost_tier=3,
        performance=AgentPerformance(
            accepted_tasks=10,
            evidence_gain_total=3,
            average_latency_ms=300_000,
            capability_reliability={"research_ecosystem": 0.4},
        ),
    )
    ranked = AgentScheduler(AgentRegistry([low, high])).rank(_work_order(), remaining_seconds=200)
    assert ranked[0].agent_id == "high"
    assert ranked[0].score > ranked[1].score


def test_scheduler_reserves_concurrency_and_releases_it_for_parallel_work():
    first = AgentManifest(
        agent_id="first",
        display_name="First",
        role="researcher",
        capabilities=["research_ecosystem"],
        tool_allowlist=["search_web"],
        concurrency_limit=1,
    )
    second = first.model_copy(update={"agent_id": "second", "display_name": "Second"})
    scheduler = AgentScheduler(AgentRegistry([first, second]))

    assert scheduler.assign(_work_order(id="WO-1"), remaining_seconds=200).agent_id == "first"
    second_task = _work_order(id="WO-2")
    assert scheduler.assign(second_task, remaining_seconds=200).agent_id == "second"
    excluded = next(item for item in second_task.assignment_trace if item.agent_id == "first")
    assert "concurrency limit reached" in excluded.exclusion_reasons

    scheduler.release("first")
    scheduler.release("second")
    assert scheduler.assign(_work_order(id="WO-3"), remaining_seconds=200).agent_id == "first"


def test_deliverable_hash_rejects_tampered_remote_artifact():
    deliverable = AgentDeliverable(
        task_id="WO-1",
        mission_id="MISSION-1",
        agent_id="remote",
        summary="accepted remote output",
    )
    payload = deliverable.model_dump(mode="json")
    payload["summary"] = "tampered in transit"
    with pytest.raises(ValueError, match="output_hash mismatch"):
        AgentDeliverable.model_validate(payload)


def test_mission_rejects_cycles_and_unknown_dependencies():
    now = datetime.now(UTC)
    first = _work_order(id="WO-1", depends_on=["WO-2"])
    second = _work_order(id="WO-2", depends_on=["WO-1"])
    with pytest.raises(ValueError, match="acyclic"):
        AgentMission(
            id="MISSION-1",
            run_id="run-1",
            project_id="project-1",
            domain="test",
            objective="test mission",
            deadline_at=now + timedelta(seconds=300),
            work_orders=[first, second],
        )


def test_planner_contract_requires_parallel_research_then_verifier_then_editor():
    with pytest.raises(ValueError, match="verifier must depend"):
        MissionPlanDraft.model_validate({
            "objective": "test",
            "planning_reason": "invalid graph",
            "tasks": [
                {"key": "aa", "task_type": "research", "objective": "a", "required_capabilities": ["research_foundations"]},
                {"key": "bb", "task_type": "research", "objective": "b", "required_capabilities": ["research_ecosystem"]},
                {"key": "vv", "task_type": "verify", "objective": "v", "required_capabilities": ["verify_claims"], "depends_on": ["aa"]},
                {"key": "ee", "task_type": "edit", "objective": "e", "required_capabilities": ["synthesize_starter_note"], "depends_on": ["vv"]},
            ],
        })


def test_provider_failover_records_safe_structured_event():
    class FailingLLM:
        async def complete(self, messages):
            raise TimeoutError("secret-bearing upstream detail")

        async def complete_structured(self, messages, response_schema):
            raise TimeoutError("secret-bearing upstream detail")

    class BackupLLM:
        async def complete(self, messages):
            return "ok"

        async def complete_structured(self, messages, response_schema):
            return response_schema(ok=True)

    llm = FailoverLLMProvider(FailingLLM(), BackupLLM(), timeout_seconds=1)
    assert asyncio.run(llm.complete([])) == "ok"
    events = llm.drain_failover_events()
    assert events == [{
        "capability": "llm",
        "operation": "complete",
        "selected_channel": "backup",
        "failed_channels": "primary:TimeoutError",
    }]
    assert "secret" not in str(events)

    class ShortExtractor:
        async def extract_url(self, url):
            return ExtractedPage(url=url, raw_text="too short")

    class BackupExtractor:
        async def extract_url(self, url):
            return ExtractedPage(url=url, raw_text="readable body " * 20)

    extraction = FailoverContentExtractionProvider(ShortExtractor(), BackupExtractor(), timeout_seconds=1)
    page = asyncio.run(extraction.extract_url("https://example.org"))
    assert len(page.raw_text) >= 120
    assert extraction.drain_failover_events()[0]["selected_channel"] == "backup"
