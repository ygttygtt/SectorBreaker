"""Project schemas."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MarketScope(StrEnum):
    CHINA = "china"
    GLOBAL = "global"
    MIXED = "mixed"
    CUSTOM = "custom"


class ResearchDepth(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ResearchProjectCreate(BaseModel):
    title: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    market_scope: MarketScope
    depth: ResearchDepth
    custom_market_scope: str | None = None

    @field_validator("title", "domain", "custom_market_scope")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("text fields cannot be blank")
        return stripped


class ResearchProject(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: str
    title: str
    domain: str
    market_scope: MarketScope
    depth: ResearchDepth
    status: ProjectStatus = ProjectStatus.DRAFT
    custom_market_scope: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
