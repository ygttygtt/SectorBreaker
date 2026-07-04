"""Pydantic models for talent-demand intelligence."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


TalentDemandPurpose = Literal[
    "hiring_profile",
    "curriculum_design",
    "capability_model",
    "market_research",
    "training",
]
Seniority = Literal["junior", "mid", "senior", "lead", "unknown"]
SkillCategory = Literal[
    "programming",
    "ai_model",
    "framework",
    "data",
    "backend",
    "product",
    "soft_skill",
    "domain",
    "other",
]


class TalentDemandInput(BaseModel):
    target_role: str
    market_scope: str = "mixed"
    region: str | None = None
    industry_scope: str | None = None
    purpose: TalentDemandPurpose = "market_research"
    user_notes: str = ""

    @field_validator("target_role", "market_scope", "user_notes", mode="before")
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class JobPostingSignal(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    salary_text: str | None = None
    experience_text: str | None = None
    education_text: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    seniority: Seniority = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class SkillDemandItem(BaseModel):
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    category: SkillCategory = "other"
    frequency: int = 0
    seniority_distribution: dict[str, int] = Field(default_factory=dict)
    representative_evidence_ids: list[str] = Field(default_factory=list)


class SourceCoverageMatrix(BaseModel):
    total_evidence: int = 0
    uploaded_jd_count: int = 0
    uploaded_report_count: int = 0
    search_result_count: int = 0
    extracted_page_count: int = 0
    occupation_standard_count: int = 0
    salary_signal_count: int = 0
    experience_signal_count: int = 0
    skill_signal_count: int = 0
    weak_or_unverified_count: int = 0
    gaps: list[str] = Field(default_factory=list)


class TalentDemandKnowledgeBase(BaseModel):
    overview: str = ""
    postings: list[JobPostingSignal] = Field(default_factory=list)
    skill_matrix: list[SkillDemandItem] = Field(default_factory=list)
    role_levels: list[str] = Field(default_factory=list)
    company_industry_patterns: list[str] = Field(default_factory=list)
    salary_experience_notes: list[str] = Field(default_factory=list)
    learning_path: list[str] = Field(default_factory=list)
    portfolio_requirements: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    source_coverage: SourceCoverageMatrix = Field(default_factory=SourceCoverageMatrix)
