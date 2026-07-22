"""Project schemas."""

from datetime import UTC, datetime
from enum import StrEnum
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MarketScope(StrEnum):
    CHINA = "china"
    GLOBAL = "global"
    MIXED = "mixed"
    CUSTOM = "custom"


class ResearchDepth(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class SourcePolicy(StrEnum):
    OPEN_WEB = "open_web"
    RELIABLE_FIRST = "reliable_first"
    RELIABLE_ONLY = "reliable_only"
    USER_MATERIALS_ONLY = "user_materials_only"


class SourceEnforcement(StrEnum):
    PREFER = "prefer"
    REQUIRE = "require"


_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


class ProjectSourcePreferences(BaseModel):
    source_pack_ids: list[str] = Field(default_factory=list, max_length=12)
    custom_allowed_domains: list[str] = Field(default_factory=list, max_length=40)
    blocked_domains: list[str] = Field(default_factory=list, max_length=40)
    enforcement: SourceEnforcement = SourceEnforcement.PREFER

    @field_validator("source_pack_ids")
    @classmethod
    def normalize_pack_ids(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values if str(value).strip()]
        return list(dict.fromkeys(normalized))

    @field_validator("custom_allowed_domains", "blocked_domains")
    @classmethod
    def normalize_domains(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_value in values:
            domain = str(raw_value).strip().lower().lstrip(".").rstrip(".")
            if not domain or not _DOMAIN_RE.fullmatch(domain):
                raise ValueError(f"invalid domain: {raw_value}")
            normalized.append(domain)
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def require_mode_needs_allow_list(self) -> "ProjectSourcePreferences":
        if (
            self.enforcement == SourceEnforcement.REQUIRE
            and not self.source_pack_ids
            and not self.custom_allowed_domains
        ):
            raise ValueError("require source enforcement needs a source pack or custom allowed domain")
        return self


class ProjectMode(StrEnum):
    DOMAIN_KNOWLEDGE = "domain_knowledge"


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
    source_policy: SourcePolicy = SourcePolicy.RELIABLE_FIRST
    project_mode: ProjectMode = ProjectMode.DOMAIN_KNOWLEDGE
    custom_market_scope: str | None = None
    source_preferences: ProjectSourcePreferences = Field(default_factory=ProjectSourcePreferences)

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
    source_policy: SourcePolicy = SourcePolicy.RELIABLE_FIRST
    project_mode: ProjectMode = ProjectMode.DOMAIN_KNOWLEDGE
    status: ProjectStatus = ProjectStatus.DRAFT
    custom_market_scope: str | None = None
    source_preferences: ProjectSourcePreferences = Field(default_factory=ProjectSourcePreferences)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResearchProjectUpdate(BaseModel):
    source_preferences: ProjectSourcePreferences
