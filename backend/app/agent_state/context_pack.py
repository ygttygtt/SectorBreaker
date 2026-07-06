"""Context selection for V2 Agent calls.

The builder is deliberately deterministic. It decides what should enter an LLM
prompt and what should stay in storage/audit logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.agent_state.models import (
    ContextPack,
    KnowledgeClaim,
    KnowledgeLayerId,
    SectorBreakerState,
    SourceMemory,
    SourceUse,
    TaskMemory,
    TrustLevel,
)


_WHITESPACE_RE = re.compile(r"\s+")
_NOISE_MARKERS = (
    "skip to content",
    "sign in",
    "navigation",
    "cookie",
    "javascript",
    "loading",
)


@dataclass(frozen=True)
class ContextPackBudget:
    max_entities: int = 10
    max_claims: int = 12
    max_sources: int = 8
    max_open_questions: int = 8
    max_chars_per_source: int = 360
    max_total_chars: int = 7000


class ContextPackBuilder:
    """Build task-specific context instead of dumping full state into prompts."""

    def __init__(self, budget: ContextPackBudget | None = None) -> None:
        self.budget = budget or ContextPackBudget()

    def build(
        self,
        state: SectorBreakerState,
        *,
        layer_id: KnowledgeLayerId | str | None = None,
        task_memory: TaskMemory | None = None,
        active_task: str = "",
    ) -> ContextPack:
        layer = state.knowledge_schema.layer(layer_id or state.current_layer_id) if (layer_id or state.current_layer_id) else None
        normalized_layer_id = layer.id if layer else None
        coverage_gaps = state.layer_coverage_gaps(normalized_layer_id) if normalized_layer_id else []
        keywords = self._keywords_for_context(state, normalized_layer_id, active_task)

        layer_key = _layer_value(normalized_layer_id) if normalized_layer_id else None
        entities = [
            f"{item.name}（{item.entity_type}）：{item.summary or '暂无摘要'}"
            for item in state.shared_knowledge.entities
            if not layer_key or layer_key in {_layer_value(layer) for layer in item.layer_ids}
        ][: self.budget.max_entities]

        claims = self._select_claims(state.shared_knowledge.claims, normalized_layer_id, keywords)
        sources, excluded, notes = self._select_sources(state.shared_knowledge.source_memories, normalized_layer_id, keywords)
        open_questions = [
            item.question
            for item in state.shared_knowledge.open_questions
            if not item.resolved and (not layer_key or layer_key in {_layer_value(layer) for layer in item.layer_ids})
        ][: self.budget.max_open_questions]

        reflection = task_memory.compressed_reflection() if task_memory else ""
        pack = ContextPack(
            goal=state.meta_context.user_goal,
            active_layer=layer,
            active_task=active_task or (task_memory.objective if task_memory else ""),
            coverage_gaps=coverage_gaps,
            entity_summaries=entities,
            claim_summaries=[
                f"{claim.text}（trust={claim.trust_level.value}, evidence={','.join(claim.evidence_ids) or '待补证'}）"
                for claim in claims
            ],
            evidence_summaries=[
                self._source_to_summary(source)
                for source in sources
            ],
            open_questions=open_questions,
            working_memory_reflection=reflection,
            included_source_memory_ids=[source.id for source in sources],
            excluded_source_memory_ids=[source.id for source in excluded],
            filter_notes=notes,
        )
        return self._enforce_total_budget(pack)

    def _select_claims(
        self,
        claims: list[KnowledgeClaim],
        layer_id: KnowledgeLayerId | str | None,
        keywords: set[str],
    ) -> list[KnowledgeClaim]:
        scored: list[tuple[int, KnowledgeClaim]] = []
        for claim in claims:
            if not claim.active or claim.hidden_from_context or claim.superseded_by:
                continue
            if layer_id and _layer_value(layer_id) not in {_layer_value(item) for item in claim.layer_ids}:
                continue
            score = 0
            if claim.evidence_ids:
                score += 3
            if claim.trust_level in {TrustLevel.HIGH, TrustLevel.MEDIUM}:
                score += 2
            if any(keyword and keyword in claim.text.lower() for keyword in keywords):
                score += 2
            if claim.needs_verification:
                score += 1
            scored.append((score, claim))
        return [claim for _, claim in sorted(scored, key=lambda item: item[0], reverse=True)[: self.budget.max_claims]]

    def _select_sources(
        self,
        sources: list[SourceMemory],
        layer_id: KnowledgeLayerId | str | None,
        keywords: set[str],
    ) -> tuple[list[SourceMemory], list[SourceMemory], list[str]]:
        scored: list[tuple[int, SourceMemory]] = []
        excluded: list[SourceMemory] = []
        notes: list[str] = []
        seen_summary_keys: set[str] = set()
        for source in sources:
            normalized_summary = self._clean_text(source.summary)
            summary_key = normalized_summary[:120].lower()
            if not source.active or source.hidden_from_context:
                excluded.append(source)
                notes.append(f"{source.id}: inactive or hidden source memory")
                continue
            if source.use == SourceUse.REJECTED:
                excluded.append(source)
                notes.append(f"{source.id}: rejected source memory")
                continue
            if self._is_noisy(normalized_summary):
                excluded.append(source)
                notes.append(f"{source.id}: noisy source text")
                continue
            if summary_key in seen_summary_keys:
                excluded.append(source)
                notes.append(f"{source.id}: duplicate summary")
                continue
            if layer_id and source.related_layer_ids and _layer_value(layer_id) not in {_layer_value(item) for item in source.related_layer_ids}:
                excluded.append(source)
                notes.append(f"{source.id}: unrelated layer")
                continue
            seen_summary_keys.add(summary_key)
            score = 0
            if source.use in {SourceUse.EVIDENCE, SourceUse.CONTEXT}:
                score += 3
            if source.trust_level in {TrustLevel.HIGH, TrustLevel.MEDIUM}:
                score += 2
            if source.evidence_ids:
                score += 2
            score += int(source.relevance_score * 3)
            if any(keyword and keyword in normalized_summary.lower() for keyword in keywords):
                score += 2
            scored.append((score, source))
        selected = [source for _, source in sorted(scored, key=lambda item: item[0], reverse=True)[: self.budget.max_sources]]
        selected_ids = {source.id for source in selected}
        excluded.extend(source for _, source in scored if source.id not in selected_ids)
        return selected, excluded, notes[:20]

    def _source_to_summary(self, source: SourceMemory) -> str:
        title = source.title or source.source_id
        text = self._clean_text(source.summary)
        if len(text) > self.budget.max_chars_per_source:
            text = text[: self.budget.max_chars_per_source - 1].rstrip(" ,.;:，。") + "…"
        evidence = ",".join(source.evidence_ids) or "待补证"
        return f"{title}: {text}（source={source.source_kind}, trust={source.trust_level.value}, evidence={evidence}）"

    def _keywords_for_context(
        self,
        state: SectorBreakerState,
        layer_id: KnowledgeLayerId | str | None,
        active_task: str,
    ) -> set[str]:
        words = {state.meta_context.domain.lower()}
        if active_task:
            words.update(token for token in re.split(r"[\s,，;；/|]+", active_task.lower()) if len(token) >= 2)
        if layer_id:
            layer = state.knowledge_schema.layer(layer_id)
            if layer:
                words.update(token for question in layer.guiding_questions for token in re.split(r"[\s,，;；/|]+", question.lower()) if len(token) >= 2)
        return words

    @staticmethod
    def _is_noisy(text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in _NOISE_MARKERS) and len(text) < 500

    def _enforce_total_budget(self, pack: ContextPack) -> ContextPack:
        while len(pack.to_prompt_text()) > self.budget.max_total_chars and pack.evidence_summaries:
            removed = pack.evidence_summaries.pop()
            pack.filter_notes.append(f"budget_trimmed: {removed[:80]}")
        while len(pack.to_prompt_text()) > self.budget.max_total_chars and pack.claim_summaries:
            removed = pack.claim_summaries.pop()
            pack.filter_notes.append(f"budget_trimmed_claim: {removed[:80]}")
        return pack

    @staticmethod
    def _clean_text(text: str) -> str:
        return _WHITESPACE_RE.sub(" ", text).strip()


def _layer_value(layer_id: KnowledgeLayerId | str | None) -> str:
    if layer_id is None:
        return ""
    return layer_id.value if isinstance(layer_id, KnowledgeLayerId) else str(layer_id)
