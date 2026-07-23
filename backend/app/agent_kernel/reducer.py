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
    known_evidence_ids: set[str] | None = None,
) -> SectorBreakerState:
    """Validate and apply useful state updates while keeping noise out."""

    _apply_state_governance_operations(state, delta)
    state.shared_knowledge.source_memories.extend(_dedupe_source_memories(state, delta))
    state.shared_knowledge.entities.extend(_dedupe_entities(state, delta))
    if known_evidence_ids is None:
        valid_evidence_ids = set(state.evidence_refs)
        valid_evidence_ids.update(delta.evidence_ids)
        valid_evidence_ids.update(observation.evidence_ids)
    else:
        valid_evidence_ids = set(known_evidence_ids)
    _apply_updated_claims(state, delta, valid_evidence_ids=valid_evidence_ids)
    state.shared_knowledge.claims.extend(_valid_new_claims(state, delta, valid_evidence_ids=valid_evidence_ids))
    state.shared_knowledge.relationships.extend(_dedupe_relationships(state, delta))
    new_open_questions = _dedupe_open_questions(state, delta)
    state.shared_knowledge.open_questions.extend(new_open_questions)
    _link_open_questions_to_layers(state, new_open_questions)
    _apply_coverage_updates(state, delta)
    if delta.delegation_notes:
        state.delegation_log.extend(delta.delegation_notes)
        state.delegation_log = state.delegation_log[-100:]
    state.evidence_refs = list(dict.fromkeys(state.evidence_refs + delta.evidence_ids + observation.evidence_ids))
    action = _state_action_for_decision(decision, observation)
    reason = observation.summary if observation.summary else decision.thought_summary
    state.add_decision(StateDecision(
        action=action,
        reason=(delta.phase_reflection or reason)[:900],
        layer_id=state.current_layer_id,
        coverage_gaps=delta.coverage_gaps,
    ))
    return state


def _apply_state_governance_operations(state: SectorBreakerState, delta: KernelStateDelta) -> None:
    deleted_sources = set(delta.deleted_source_ids)
    if deleted_sources:
        state.shared_knowledge.source_memories = [
            source for source in state.shared_knowledge.source_memories
            if source.id not in deleted_sources and source.source_id not in deleted_sources
        ]
    hidden_sources = set(delta.hidden_source_ids)
    for source in state.shared_knowledge.source_memories:
        if source.id in hidden_sources or source.source_id in hidden_sources:
            source.hidden_from_context = True
            source.active = False
            source.filter_reason = source.filter_reason or "hidden by state delta"

    deleted_claims = set(delta.deleted_claim_ids)
    if deleted_claims:
        state.shared_knowledge.claims = [claim for claim in state.shared_knowledge.claims if claim.id not in deleted_claims]
    hidden_claims = set(delta.hidden_claim_ids)
    superseded_claims = set(delta.superseded_claim_ids)
    for claim in state.shared_knowledge.claims:
        if claim.id in hidden_claims:
            claim.hidden_from_context = True
            claim.active = False
            claim.revision_reason = claim.revision_reason or "hidden by state delta"
        if claim.id in superseded_claims:
            claim.active = False
            claim.hidden_from_context = True
            claim.revision_reason = claim.revision_reason or "superseded by newer claim"

    resolved_questions = set(delta.resolved_open_question_ids)
    for question in state.shared_knowledge.open_questions:
        if question.id in resolved_questions:
            question.resolved = True
            question.status = "resolved"


def _apply_updated_claims(
    state: SectorBreakerState,
    delta: KernelStateDelta,
    *,
    valid_evidence_ids: set[str],
) -> None:
    if not delta.updated_claims:
        return
    existing = {claim.id: claim for claim in state.shared_knowledge.claims}
    for updated in delta.updated_claims:
        updated = _downgrade_claim_without_valid_evidence(updated, valid_evidence_ids)
        if updated.id in existing:
            index = state.shared_knowledge.claims.index(existing[updated.id])
            state.shared_knowledge.claims[index] = updated
            continue
        similar = _find_semantically_similar_claim(state.shared_knowledge.claims, updated)
        if similar is not None:
            updated.supersedes = list(dict.fromkeys(updated.supersedes + [similar.id]))
            similar.superseded_by = updated.id
            similar.active = False
            similar.hidden_from_context = True
        state.shared_knowledge.claims.append(updated)


def _apply_coverage_updates(state: SectorBreakerState, delta: KernelStateDelta) -> None:
    for update in delta.coverage_updates:
        layer_id = update.get("layer_id")
        if not layer_id:
            continue
        layer = state.knowledge_schema.layer(str(layer_id))
        if layer is None:
            continue
        if "coverage_score" in update:
            layer.coverage_score = max(0.0, min(1.0, float(update["coverage_score"])))
        if "coverage_status" in update:
            try:
                layer.coverage_status = type(layer.coverage_status)(str(update["coverage_status"]))
            except ValueError:
                pass
        if "coverage_notes" in update:
            layer.coverage_notes = str(update["coverage_notes"])[:1200]
        if "ready_to_write" in update:
            layer.ready_to_write = bool(update["ready_to_write"])
        if "evidence_count" in update:
            layer.evidence_count = max(0, int(update["evidence_count"]))
        if "claim_count" in update:
            layer.claim_count = max(0, int(update["claim_count"]))
        if "open_question_count" in update:
            layer.open_question_count = max(0, int(update["open_question_count"]))


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


def _valid_new_claims(state: SectorBreakerState, delta: KernelStateDelta, *, valid_evidence_ids: set[str]):
    seen = {_norm(item.text) for item in state.shared_knowledge.claims}
    result = []
    for claim in delta.claims:
        claim = _downgrade_claim_without_valid_evidence(claim, valid_evidence_ids)
        key = _norm(claim.text)
        if key in seen:
            continue
        similar = _find_semantically_similar_claim(state.shared_knowledge.claims + result, claim)
        if similar is not None:
            similar.conflicts_with = list(dict.fromkeys(similar.conflicts_with + [claim.id]))
            continue
        seen.add(key)
        result.append(claim)
    return result


def _downgrade_claim_without_valid_evidence(claim, valid_evidence_ids: set[str]):
    valid_ids = [item for item in claim.evidence_ids if item in valid_evidence_ids]
    if claim.verification_status != "verified":
        return claim
    if not valid_ids:
        return claim.model_copy(update={
            "evidence_ids": [],
            "verification_status": "unverified",
            "needs_verification": True,
            "notes": (claim.notes + "; " if claim.notes else "") + "verified claim downgraded: no project evidence",
        })
    if len(valid_ids) != len(claim.evidence_ids):
        return claim.model_copy(update={
            "evidence_ids": valid_ids,
            "verification_status": "partially_verified",
            "needs_verification": True,
            "notes": (claim.notes + "; " if claim.notes else "") + "some evidence ids were not found in the project",
        })
    return claim


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
        (_norm(item.question), tuple(sorted(_layer_value(layer) for layer in item.layer_ids)))
        for item in state.shared_knowledge.open_questions
    }
    result = []
    for question in delta.open_questions:
        key = (_norm(question.question), tuple(sorted(_layer_value(layer) for layer in question.layer_ids)))
        if key in seen:
            continue
        seen.add(key)
        result.append(question)
    return result


def _link_open_questions_to_layers(state: SectorBreakerState, questions) -> None:
    for question in questions:
        for raw_layer_id in question.layer_ids or ([question.parent_layer_id] if question.parent_layer_id else []):
            layer = state.knowledge_schema.layer(raw_layer_id)
            if layer is None:
                continue
            if question.id not in layer.open_question_ids:
                layer.open_question_ids.append(question.id)
            if question.parent_layer_id and question.id not in layer.drill_down_task_ids:
                layer.drill_down_task_ids.append(question.id)


def _norm(text: str) -> str:
    return _SPACE_RE.sub("", text.strip().lower())


def _find_semantically_similar_claim(existing_claims, new_claim):
    new_tokens = _semantic_tokens(new_claim.text)
    if len(new_tokens) < 3:
        return None
    for claim in existing_claims:
        if not getattr(claim, "active", True) or getattr(claim, "hidden_from_context", False):
            continue
        tokens = _semantic_tokens(claim.text)
        if not tokens:
            continue
        overlap = len(tokens & new_tokens) / max(len(tokens | new_tokens), 1)
        shared_evidence = set(claim.evidence_ids) & set(new_claim.evidence_ids)
        if overlap >= 0.62 or (overlap >= 0.42 and shared_evidence):
            return claim
    return None


def _semantic_tokens(text: str) -> set[str]:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text.lower())
    raw_tokens = {item for item in normalized.split() if len(item) >= 2}
    chinese_chunks = {normalized[index:index + 2] for index in range(max(0, len(normalized) - 1)) if "\u4e00" <= normalized[index] <= "\u9fff"}
    stopwords = {"the", "and", "for", "with", "需要", "一个", "这个", "可以", "以及"}
    return {token for token in raw_tokens | chinese_chunks if token not in stopwords}


def _layer_value(layer_id) -> str:
    return layer_id.value if hasattr(layer_id, "value") else str(layer_id)
