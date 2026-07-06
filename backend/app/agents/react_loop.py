"""Generic bounded ReAct loop primitives.

This module does not call LLMs directly. It defines the execution contract that
Master/Specialist Agents can use when backed by an LLM policy and provider
tools.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.app.agent_state.models import AgentAction, KnowledgeLayerId


class StopReason(StrEnum):
    SUFFICIENT = "sufficient"
    MAX_STEPS = "max_steps"
    BLOCKED = "blocked"
    ASK_USER = "ask_user"
    DEGRADED = "degraded"


class ThoughtSummary(BaseModel):
    text: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    missing_information: list[str] = Field(default_factory=list)


class ToolCallRequest(BaseModel):
    tool: str
    action: str
    query: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class Observation(BaseModel):
    tool: str
    summary: str
    success: bool = True
    useful: bool = True
    evidence_ids: list[str] = Field(default_factory=list)
    raw_ref: str | None = None


class StateDelta(BaseModel):
    entity_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    source_memory_ids: list[str] = Field(default_factory=list)
    open_question_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.entity_ids
            or self.claim_ids
            or self.source_memory_ids
            or self.open_question_ids
            or self.notes
        )


class ReActStep(BaseModel):
    step_id: str = Field(default_factory=lambda: f"RA-{uuid4().hex[:12]}")
    thought: ThoughtSummary
    tool_call: ToolCallRequest | None = None
    observation: Observation | None = None
    state_delta: StateDelta = Field(default_factory=StateDelta)
    decision: AgentAction = AgentAction.CONTINUE


class ReActRunResult(BaseModel):
    task_id: str
    layer_id: KnowledgeLayerId | None = None
    steps: list[ReActStep] = Field(default_factory=list)
    stop_reason: StopReason
    final_summary: str
    state_delta: StateDelta = Field(default_factory=StateDelta)


PolicyFn = Callable[[list[ReActStep]], Awaitable[ReActStep]]
ToolDispatcher = Callable[[ToolCallRequest], Awaitable[Observation]]


class BoundedReActRunner:
    """Run a ReAct policy with max-step protection and structured observations."""

    def __init__(self, *, max_steps: int = 5) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        self.max_steps = max_steps

    async def run(
        self,
        *,
        task_id: str,
        policy: PolicyFn,
        tool_dispatcher: ToolDispatcher,
        layer_id: KnowledgeLayerId | None = None,
    ) -> ReActRunResult:
        steps: list[ReActStep] = []
        aggregate_delta = StateDelta()
        stop_reason = StopReason.MAX_STEPS
        for _ in range(self.max_steps):
            step = await policy(steps)
            if step.tool_call is not None and step.observation is None:
                step.observation = await tool_dispatcher(step.tool_call)
            aggregate_delta = self._merge_delta(aggregate_delta, step.state_delta)
            steps.append(step)
            if step.decision == AgentAction.BLOCK:
                stop_reason = StopReason.BLOCKED
                break
            if step.decision == AgentAction.ASK_USER:
                stop_reason = StopReason.ASK_USER
                break
            if step.decision == AgentAction.DEGRADE:
                stop_reason = StopReason.DEGRADED
                break
            if step.decision in {AgentAction.CONTINUE, AgentAction.EXPORT} and step.tool_call is None:
                stop_reason = StopReason.SUFFICIENT
                break
        final_summary = self._summarize(steps, stop_reason)
        return ReActRunResult(
            task_id=task_id,
            layer_id=layer_id,
            steps=steps,
            stop_reason=stop_reason,
            final_summary=final_summary,
            state_delta=aggregate_delta,
        )

    @staticmethod
    def _merge_delta(left: StateDelta, right: StateDelta) -> StateDelta:
        return StateDelta(
            entity_ids=list(dict.fromkeys(left.entity_ids + right.entity_ids)),
            claim_ids=list(dict.fromkeys(left.claim_ids + right.claim_ids)),
            source_memory_ids=list(dict.fromkeys(left.source_memory_ids + right.source_memory_ids)),
            open_question_ids=list(dict.fromkeys(left.open_question_ids + right.open_question_ids)),
            notes=list(dict.fromkeys(left.notes + right.notes)),
        )

    @staticmethod
    def _summarize(steps: list[ReActStep], stop_reason: StopReason) -> str:
        if not steps:
            return f"ReAct 未执行步骤，停止原因：{stop_reason.value}"
        useful_observations = [
            step.observation.summary
            for step in steps
            if step.observation is not None and step.observation.useful
        ]
        latest_thought = steps[-1].thought.text
        if useful_observations:
            return f"停止原因：{stop_reason.value}。最新判断：{latest_thought}。有效观察：{'；'.join(useful_observations[-3:])}"
        return f"停止原因：{stop_reason.value}。最新判断：{latest_thought}"
