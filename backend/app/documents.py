"""Document parsing utilities for uploaded reports and notes."""

from __future__ import annotations

import re

from backend.app.schemas.documents import DocumentCitation, DocumentSegment

_URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")


def split_document_segments(document_id: str, content: str) -> list[DocumentSegment]:
    normalized = content.replace("\r\n", "\n").strip()
    if not normalized:
        return [
            DocumentSegment(
                id=f"{document_id}-seg-001",
                document_id=document_id,
                order_index=1,
                text="",
                char_count=0,
                citation_refs=[],
            )
        ]

    chunks = re.split(r"\n\s*\n+", normalized)
    segments: list[DocumentSegment] = []
    for index, chunk in enumerate(chunks, start=1):
        lines = [line.rstrip() for line in chunk.splitlines()]
        heading = None
        if lines and lines[0].lstrip().startswith("#"):
            heading = lines[0].lstrip("# ").strip() or None
        citation_refs = _URL_PATTERN.findall(chunk)
        segments.append(
            DocumentSegment(
                id=f"{document_id}-seg-{index:03d}",
                document_id=document_id,
                order_index=index,
                heading=heading,
                text=chunk.strip(),
                char_count=len(chunk.strip()),
                citation_refs=citation_refs,
            )
        )
    return segments


def extract_document_citations(document_id: str, segments: list[DocumentSegment]) -> list[DocumentCitation]:
    citation_map: dict[str, list[str]] = {}
    for segment in segments:
        for url in segment.citation_refs:
            citation_map.setdefault(url, []).append(segment.id)

    citations: list[DocumentCitation] = []
    for index, (url, segment_ids) in enumerate(citation_map.items(), start=1):
        citations.append(
            DocumentCitation(
                id=f"{document_id}-cit-{index:03d}",
                document_id=document_id,
                raw_reference=url,
                source_url=url,
                referenced_segment_ids=segment_ids,
            )
        )
    return citations
