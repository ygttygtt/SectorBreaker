"""Project-local retrieval across evidence, documents, and artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.storage.sqlite import SQLiteRepository


@dataclass(frozen=True)
class ProjectRagCitation:
    source_id: str
    source_type: str
    title: str
    snippet: str
    score: float
    url: str | None = None
    relative_path: str | None = None
    content_hash: str | None = None
    verification_status: str | None = None


class ProjectRetriever:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def retrieve(self, project_id: str, query: str, limit: int = 6) -> list[ProjectRagCitation]:
        candidates: list[ProjectRagCitation] = []
        candidates.extend(self._fts_candidates(project_id, query, limit))
        candidates.extend(self._evidence_candidates(project_id, query))
        candidates.extend(self._document_candidates(project_id, query))
        candidates.extend(self._artifact_candidates(project_id, query))
        deduped: dict[str, ProjectRagCitation] = {}
        for item in sorted(candidates, key=lambda citation: citation.score, reverse=True):
            if item.source_id not in deduped:
                deduped[item.source_id] = item
        return list(deduped.values())[:limit]

    def _fts_candidates(self, project_id: str, query: str, limit: int) -> list[ProjectRagCitation]:
        try:
            results = self.repository.search_project(project_id, query, limit=limit)
        except Exception:
            return []
        evidence_by_id = {item.id: item for item in self.repository.list_evidence(project_id)}
        candidates: list[ProjectRagCitation] = []
        for result in results:
            evidence = evidence_by_id.get(result.document_id)
            candidates.append(ProjectRagCitation(
                source_id=result.document_id,
                source_type="evidence",
                title=evidence.source_title if evidence else result.document_id,
                snippet=_shorten(result.snippet, 360),
                score=1.0 + result.score,
                url=evidence.source_url if evidence else None,
                verification_status=evidence.verification_status.value if evidence else None,
            ))
        return candidates

    def _evidence_candidates(self, project_id: str, query: str) -> list[ProjectRagCitation]:
        return [
            ProjectRagCitation(
                source_id=item.id,
                source_type="evidence",
                title=item.source_title,
                snippet=_shorten(item.summary or item.snippet or item.raw_excerpt or item.source_title, 360),
                score=_score(query, " ".join([item.source_title, item.snippet, item.summary or ""])),
                url=item.source_url,
                verification_status=item.verification_status.value,
            )
            for item in self.repository.list_evidence(project_id)
            if _score(query, " ".join([item.source_title, item.snippet, item.summary or ""])) > 0
        ]

    def _document_candidates(self, project_id: str, query: str) -> list[ProjectRagCitation]:
        candidates: list[ProjectRagCitation] = []
        for document in self.repository.list_documents(project_id):
            doc_score = _score(query, f"{document.file_name or ''}\n{document.content}")
            if doc_score > 0:
                candidates.append(ProjectRagCitation(
                    source_id=document.id,
                    source_type=f"document:{document.channel}",
                    title=document.file_name or document.id,
                    snippet=_shorten_around_query(document.content, query, 360),
                    score=doc_score * 0.9,
                    relative_path=document.file_name,
                ))
            for segment in self.repository.list_document_segments(document.id):
                seg_score = _score(query, segment.text)
                if seg_score <= 0:
                    continue
                candidates.append(ProjectRagCitation(
                    source_id=segment.id,
                    source_type=f"document_segment:{document.channel}",
                    title=segment.heading or document.file_name or document.id,
                    snippet=_shorten_around_query(segment.text, query, 360),
                    score=seg_score,
                    relative_path=document.file_name,
                ))
        return candidates

    def _artifact_candidates(self, project_id: str, query: str) -> list[ProjectRagCitation]:
        candidates: list[ProjectRagCitation] = []
        for artifact in self.repository.list_artifacts(project_id):
            score = _score(query, f"{artifact.title}\n{artifact.content}")
            if score <= 0:
                continue
            candidates.append(ProjectRagCitation(
                source_id=artifact.id,
                source_type="artifact",
                title=artifact.title,
                snippet=_shorten_around_query(artifact.content, query, 360),
                score=score * 0.85,
                relative_path=artifact.content_path,
                content_hash=artifact.content_hash,
            ))
        return candidates


def _score(query: str, text: str) -> float:
    terms = _terms(query)
    if not terms:
        return 0.0
    lowered = text.lower()
    hits = 0
    for term in terms:
        if term in lowered:
            hits += 1
    if hits == 0 and any(char in lowered for char in query.lower() if "\u4e00" <= char <= "\u9fff"):
        hits = 1
    return hits / len(terms)


def _terms(text: str) -> list[str]:
    lowered = text.lower()
    terms = re.findall(r"[a-z0-9_+#.-]{2,}|[\u4e00-\u9fff]{2,}", lowered)
    return list(dict.fromkeys(terms))


def _shorten(text: str, max_chars: int) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip(" ,.;:，。") + "…"


def _shorten_around_query(text: str, query: str, max_chars: int) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    lowered = normalized.casefold()
    positions = [lowered.find(term) for term in _terms(query)]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return _shorten(normalized, max_chars)
    hit = min(positions)
    start = max(0, hit - max_chars // 3)
    end = min(len(normalized), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    snippet = normalized[start:end].strip(" ,.;:，。")
    return ("…" if start else "") + snippet + ("…" if end < len(normalized) else "")
