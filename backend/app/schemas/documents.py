"""Document ingestion schemas."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class ProjectDocumentCreate(BaseModel):
    channel: str = Field(min_length=1)
    content: str = Field(min_length=1)
    file_name: str | None = None
    mime_type: str | None = None

    @field_validator("channel", "content", "file_name", "mime_type")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("text fields cannot be blank")
        return stripped


class ProjectDocument(BaseModel):
    id: str
    project_id: str
    channel: str
    file_name: str | None = None
    mime_type: str | None = None
    content: str
    word_count: int = 0
    char_count: int = 0
    segment_count: int = 1
    citation_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocumentSegment(BaseModel):
    id: str
    document_id: str
    order_index: int
    text: str
    heading: str | None = None
    char_count: int = 0
    citation_refs: list[str] = Field(default_factory=list)


class DocumentCitation(BaseModel):
    id: str
    document_id: str
    raw_reference: str
    source_title: str | None = None
    source_url: str | None = None
    referenced_segment_ids: list[str] = Field(default_factory=list)
