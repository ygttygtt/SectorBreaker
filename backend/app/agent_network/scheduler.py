"""Deterministic, explainable WorkOrder assignment."""

from __future__ import annotations

from statistics import mean

from backend.app.agent_network.registry import AgentRegistry
from backend.app.schemas import AgentBid, AgentManifest, TaskSettlement, WorkOrder
from backend.app.storage.sqlite import SQLiteRepository


class AgentScheduler:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry
        self._active: dict[str, int] = {}

    def rank(self, work_order: WorkOrder, *, remaining_seconds: float) -> list[AgentBid]:
        bids = [self._bid(manifest, work_order, remaining_seconds) for manifest in self.registry.list()]
        return sorted(
            bids,
            key=lambda item: (
                not item.eligible,
                -item.score,
                self.registry.get(item.agent_id).cost_tier,
                self.registry.get(item.agent_id).performance.rejected_tasks,
                item.agent_id,
            ),
        )

    def assign(self, work_order: WorkOrder, *, remaining_seconds: float) -> AgentManifest:
        bids = self.rank(work_order, remaining_seconds=remaining_seconds)
        work_order.assignment_trace = bids
        winner = next((bid for bid in bids if bid.eligible), None)
        if winner is None:
            reasons = sorted({reason for bid in bids for reason in bid.exclusion_reasons})
            raise RuntimeError("no eligible agent: " + "; ".join(reasons))
        work_order.assigned_agent_id = winner.agent_id
        self._active[winner.agent_id] = self._active.get(winner.agent_id, 0) + 1
        return self.registry.get(winner.agent_id)

    def release(self, agent_id: str) -> None:
        active = self._active.get(agent_id, 0)
        if active <= 1:
            self._active.pop(agent_id, None)
        else:
            self._active[agent_id] = active - 1

    def _bid(self, manifest: AgentManifest, work_order: WorkOrder, remaining_seconds: float) -> AgentBid:
        required = set(work_order.required_capabilities)
        provided = set(manifest.capabilities)
        matched = len(required & provided)
        capability_match = matched / max(1, len(required))
        exclusions: list[str] = []
        if not manifest.available:
            exclusions.append("transport unavailable")
        if self._active.get(manifest.agent_id, 0) >= manifest.concurrency_limit:
            exclusions.append("concurrency limit reached")
        if capability_match < 1.0:
            exclusions.append("missing required capabilities")
        if remaining_seconds < min(15, work_order.budget.deadline_seconds):
            exclusions.append("insufficient remaining deadline")
        reliability = mean(
            [manifest.performance.reliability_for(capability) for capability in required]
            or [0.5]
        )
        accepted = manifest.performance.accepted_tasks
        evidence_gain = (
            min(1.0, manifest.performance.evidence_gain_total / max(1, accepted) / 3)
            if accepted
            else 0.5
        )
        budget_fit = (4 - manifest.cost_tier) / 3
        latency = manifest.performance.average_latency_ms
        latency_fit = 0.7 if latency <= 0 else max(0.0, min(1.0, 120_000 / latency))
        eligible = not exclusions
        score = (
            0.40 * capability_match
            + 0.25 * reliability
            + 0.15 * evidence_gain
            + 0.10 * budget_fit
            + 0.10 * latency_fit
        ) if eligible else 0.0
        return AgentBid(
            agent_id=manifest.agent_id,
            eligible=eligible,
            score=round(score, 4),
            capability_match=capability_match,
            reliability=reliability,
            evidence_gain=evidence_gain,
            budget_fit=budget_fit,
            latency_fit=latency_fit,
            exclusion_reasons=exclusions,
            rationale=(
                f"capability={capability_match:.2f}, reliability={reliability:.2f}, "
                f"evidence_gain={evidence_gain:.2f}, budget_fit={budget_fit:.2f}, "
                f"latency_fit={latency_fit:.2f}"
            ),
        )


def persist_settlement(
    repository: SQLiteRepository,
    project_id: str,
    manifest: AgentManifest,
    settlement: TaskSettlement,
    capability: str,
    *,
    latency_ms: int,
) -> AgentManifest:
    performance = manifest.performance.model_copy(deep=True)
    old_assigned = performance.assigned_tasks
    performance.assigned_tasks += 1
    if settlement.accepted:
        performance.accepted_tasks += 1
    else:
        performance.rejected_tasks += 1
    performance.rework_count += settlement.rework_count
    performance.evidence_gain_total += settlement.evidence_gain
    performance.average_latency_ms = (
        (performance.average_latency_ms * old_assigned + latency_ms)
        / max(1, performance.assigned_tasks)
    )
    performance.average_duplicate_ratio = (
        (performance.average_duplicate_ratio * old_assigned + settlement.duplicate_ratio)
        / max(1, performance.assigned_tasks)
    )
    performance.capability_reliability[capability] = settlement.reliability_after
    repository.save_agent_performance(project_id, manifest.agent_id, performance)
    return manifest.model_copy(update={"performance": performance})
