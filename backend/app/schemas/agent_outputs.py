"""Structured business-agent output schemas."""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ScopeKeyQuestion(BaseModel):
    question: str = ""
    importance: str = ""
    source: str = ""
    common_mistake: str = ""
    priority_1h: str = ""


class ScopeDataCaliberItem(BaseModel):
    metric: str = ""
    caliber: str = ""
    confusion: str = ""
    suitable_for: str = ""
    not_suitable_for: str = ""
    recommended_source: str = ""


class ScopeAnalysisOutput(BaseModel):
    domain_definition: str = ""
    boundaries: str = ""
    common_confusions: list[str] = Field(default_factory=list)
    key_questions: list[ScopeKeyQuestion] = Field(default_factory=list)
    data_caliber: list[ScopeDataCaliberItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_keys(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        raw_questions = payload.get("key_questions") or payload.get("questions") or []
        normalized_questions: list[dict[str, str]] = []
        for item in raw_questions:
            if isinstance(item, str):
                normalized_questions.append({"question": item})
            elif isinstance(item, dict):
                normalized_questions.append(item)
        payload["key_questions"] = normalized_questions
        payload["common_confusions"] = [
            str(item)
            for item in (payload.get("common_confusions") or [])
            if item
        ]
        return payload


class ResearchFrameOutput(BaseModel):
    sections: list[str] = Field(default_factory=list)
    key_questions: list[str] = Field(default_factory=list)
    learning_path: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_keys(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        raw_questions = (
            payload.get("key_questions")
            or payload.get("key_questions_list")
            or payload.get("questions")
            or payload.get("关键问题")
            or []
        )
        normalized_questions: list[str] = []
        for item in raw_questions:
            if isinstance(item, str):
                normalized_questions.append(item)
            elif isinstance(item, dict):
                question = (
                    item.get("question")
                    or item.get("title")
                    or item.get("text")
                    or item.get("importance")
                    or item.get("source")
                )
                if question:
                    normalized_questions.append(str(question))
        payload["key_questions"] = normalized_questions
        payload["sections"] = [
            str(item)
            for item in (
                payload.get("sections")
                or payload.get("topics")
                or payload.get("研究板块")
                or []
            )
            if item
        ]
        payload["learning_path"] = [str(item) for item in (payload.get("learning_path") or []) if item]
        return payload


class MarkdownArtifactOutput(BaseModel):
    title: str = ""
    content: str = ""


class MarketAnalysisOutput(MarkdownArtifactOutput):
    facts: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class PlayerAnalysisOutput(MarkdownArtifactOutput):
    players: list[dict[str, Any]] = Field(default_factory=list)


class TransactionUnitOutput(BaseModel):
    name: str = ""
    why_buy: str = ""
    price_range: str = ""
    frequency: str = ""
    repurchase_cycle: str = ""
    decision_cost: str = ""
    delivery_difficulty: str = ""
    risks: str = ""
    margin_source: str = ""
    selling_points: str = ""
    user_keywords: str = ""


class TransactionAnalysisOutput(BaseModel):
    units: list[TransactionUnitOutput] = Field(default_factory=list)
    title: str = ""
    content: str = ""


class OpportunityHypothesisOutput(BaseModel):
    name: str = ""
    logic: str = ""
    target_users: str = ""
    underserved: str = ""
    barriers: str = ""
    resources: str = ""
    risks: str = ""
    validate_week1: str = ""


class SynthesisOutput(BaseModel):
    title: str = ""
    content: str = ""
    overall: str = ""
    hypotheses: list[OpportunityHypothesisOutput] = Field(default_factory=list)


class KnowledgeMapOutput(MarkdownArtifactOutput):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    learning_order: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
