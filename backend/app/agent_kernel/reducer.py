"""Apply Agent Kernel state deltas to SectorBreakerState."""

from __future__ import annotations

import re

from backend.app.agent_kernel.models import AgentDecision, KernelObservation, KernelStateDelta
from backend.app.agent_state.models import AgentAction, AgentDecision as StateDecision, SectorBreakerState


_SPACE_RE = re.compile(r"\s+")


def apply_state_delta(
    state: SectorBreakerState,
    delta: KernelStateDelta,
    *,
    decision: AgentDecision,
    observation: KernelObservation,
) -> SectorBreakerState:
    """Validate and apply useful state updates while keeping noise out."""

    state.shared_knowledge.source_memories.extend(_dedupe_source_memories(state, delta))
    state.shared_knowledge.entities.extend(_dedupe_entities(state, delta))
    state.shared_knowledge.claims.extend(_valid_new_claims(state, delta))
    state.shared_knowledge.relationships.extend(_dedupe_relationships(state, delta))
    state.shared_knowledge.open_questions.extend(_dedupe_open_questions(state, delta))
    state.evidence_refs = list(dict.fromkeys(state.evidence_refs + delta.evidence_ids + observation.evidence_ids))
    action = _state_action_for_decision(decision, observation)
    reason = observation.summary if observation.summary else decision.thought_summary
    state.add_decision(StateDecision(
        action=action,
        reason=reason[:900],
        layer_id=state.current_layer_id,
        coverage_gaps=delta.coverage_gaps,
    ))
    return state


def _state_action_for_decision(decision: AgentDecision, observation: KernelObservation) -> AgentAction:
    if decision.action_type.value == "ask_user" or observation.requires_human:
        return AgentAction.ASK_USER
    if decision.action_type.value == "block" or not observation.success:
        return AgentAction.BLOCK if decision.action_type.value == "block" else AgentAction.DEGRADE
    if decision.action_type.value == "finish":
        return AgentAction.EXPORT
    if decision.action_type.value == "call_tool" and decision.tool_call and decision.tool_call.tool_name == "search_web":
        return AgentAction.SEARCH_AGAIN
    return AgentAction.CONTINUE


def _dedupe_source_memories(state: SectorBreakerState, delta: KernelStateDelta):
    seen = {item.source_id for item in state.shared_knowledge.source_memories}
    result = []
    for source in delta.source_memories:
        key = source.source_id or _norm(source.summary[:120])
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _dedupe_entities(state: SectorBreakerState, delta: KernelStateDelta):
    seen = {(_norm(item.name), item.entity_type) for item in state.shared_knowledge.entities}
    result = []
    for entity in delta.entities:
        key = (_norm(entity.name), entity.entity_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(entity)
    return result


def _valid_new_claims(state: SectorBreakerState, delta: KernelStateDelta):
    seen = {_norm(item.text) for item in state.shared_knowledge.claims}
    result = []
    for claim in delta.claims:
        if claim.verification_status == "verified" and not claim.evidence_ids:
            continue
        key = _norm(claim.text)
        if key in seen:
            continue
        seen.add(key)
        result.append(claim)
    return result


def _dedupe_relationships(state: SectorBreakerState, delta: KernelStateDelta):
    seen = {
        (item.source_entity_id, item.target_entity_id, item.relationship_type)
        for item in state.shared_knowledge.relationships
    }
    result = []
    for relationship in delta.relationships:
        key = (
            relationship.source_entity_id,
            relationship.target_entity_id,
            relationship.relationship_type,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(relationship)
    return result


def _dedupe_open_questions(state: SectorBreakerState, delta: KernelStateDelta):
    seen = {
        (_norm(item.question), tuple(sorted(layer.value for layer in item.layer_ids)))
        for item in state.shared_knowledge.open_questions
    }
    result = []
    for question in delta.open_questions:
        key = (_norm(question.question), tuple(sorted(layer.value for layer in question.layer_ids)))
        if key in seen:
            continue
        seen.add(key)
        result.append(question)
    return result


def _norm(text: str) -> str:
    return _SPACE_RE.sub("", text.strip().lower())
