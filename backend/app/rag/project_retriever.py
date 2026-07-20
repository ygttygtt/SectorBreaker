"""Shared local lexical/vector hybrid retrieval for project knowledge."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from backend.app.providers.interfaces import EmbeddingProvider
from backend.app.rag.vector_index import ProjectVectorIndex, VectorCandidate, VectorSyncResult
from backend.app.storage.sqlite import SQLiteRepository


@dataclass(frozen=True)
class ProjectRagCitation:
    source_id: str
    source_type: str
    title: str
    snippet: str
    score: float
    parent_id: str | None = None
    url: str | None = None
    relative_path: str | None = None
    content_hash: str | None = None
    verification_status: str | None = None
    retrieval_mode: str = "lexical"
    lexical_rank: int | None = None
    vector_rank: int | None = None
    lexical_score: float | None = None
    vector_score: float | None = None
    embedding_model: str | None = None


@dataclass(frozen=True)
class RetrievalDiagnostics:
    effective_mode: str
    embedding_configured: bool = False
    embedding_available: bool = False
    embedding_loaded: bool = False
    embedding_provider: str | None = None
    embedding_model: str | None = None
    dimension: int | None = None
    index_count: int = 0
    lexical_candidates: int = 0
    vector_candidates: int = 0
    last_error: str | None = None


class ProjectRetriever:
    def __init__(
        self,
        repository: SQLiteRepository,
        embedding_provider: EmbeddingProvider | None = None,
        *,
        embedding_mode: str = "disabled",
        rrf_k: int = 60,
        min_vector_score: float = 0.25,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        normalized_mode = (embedding_mode or "disabled").strip().lower()
        self.embedding_mode = (
            "disabled"
            if normalized_mode in {"disabled", "none", "off"}
            else normalized_mode
        )
        self.rrf_k = max(1, rrf_k)
        self.min_vector_score = min_vector_score
        self.vector_index = (
            ProjectVectorIndex(repository, embedding_provider)
            if embedding_provider is not None
            else None
        )
        if embedding_provider is not None:
            initial_mode = "hybrid_pending"
            initial_error = None
        elif self.embedding_mode == "disabled":
            initial_mode = "lexical"
            initial_error = None
        else:
            initial_mode = "lexical_degraded"
            initial_error = "embedding provider unavailable"
        self.last_diagnostics = RetrievalDiagnostics(
            effective_mode=initial_mode,
            embedding_configured=embedding_provider is not None,
            last_error=initial_error,
        )
        self._initial_diagnostics = self.last_diagnostics
        self._project_diagnostics: dict[str, RetrievalDiagnostics] = {}

    def retrieve(self, project_id: str, query: str, limit: int = 6) -> list[ProjectRagCitation]:
        results, _ = self.retrieve_with_diagnostics(project_id, query, limit)
        return results

    def retrieve_with_diagnostics(
        self,
        project_id: str,
        query: str,
        limit: int = 6,
    ) -> tuple[list[ProjectRagCitation], RetrievalDiagnostics]:
        """Retrieve citations and the diagnostics from the same invocation.

        Returning diagnostics together avoids cross-request attribution bugs when
        multiple chat or Agent Kernel calls share one production retriever.
        """
        lexical = self._dedupe_lexical(self._lexical_candidates(project_id, query, max(limit * 3, 12)))
        vector: list[VectorCandidate] = []
        vector_error: str | None = None
        sync: VectorSyncResult | None = None
        if self.vector_index is not None:
            try:
                vector_result, sync = self.vector_index.search_with_sync(
                    project_id,
                    query,
                    limit=max(limit * 3, 12),
                )
                vector = [
                    item for item in vector_result
                    if item.similarity >= self.min_vector_score
                ]
            except Exception as exc:
                vector_error = f"{type(exc).__name__}: {exc}"

        results = self._fuse(lexical, vector, limit=limit)
        if self.vector_index is None:
            effective_mode = "lexical" if self.embedding_mode == "disabled" else "lexical_degraded"
            vector_error = None if self.embedding_mode == "disabled" else "embedding provider unavailable"
        elif vector_error:
            effective_mode = "lexical_degraded"
        else:
            effective_mode = "hybrid"
        info = self.embedding_provider.info() if self.embedding_provider is not None else None
        diagnostics = RetrievalDiagnostics(
            effective_mode=effective_mode,
            embedding_configured=self.embedding_provider is not None,
            embedding_available=info.available if info else False,
            embedding_loaded=info.loaded if info else False,
            embedding_provider=info.provider if info else None,
            embedding_model=info.model if info else None,
            dimension=(sync.dimension if sync else None) or (info.dimension if info else None),
            index_count=(
                sync.index_count
                if sync
                else self._current_index_count(project_id)
            ),
            lexical_candidates=len(lexical),
            vector_candidates=len(vector),
            last_error=vector_error or (info.last_error if info else None),
        )
        self.last_diagnostics = diagnostics
        self._project_diagnostics[project_id] = diagnostics
        return results, diagnostics

    def rebuild_vector_index(self, project_id: str) -> VectorSyncResult:
        if self.vector_index is None:
            raise RuntimeError("local embedding provider is not configured")
        try:
            result = self.vector_index.rebuild_project(project_id)
        except Exception as exc:
            info = self.embedding_provider.info() if self.embedding_provider else None
            diagnostics = RetrievalDiagnostics(
                effective_mode="lexical_degraded",
                embedding_configured=True,
                embedding_available=info.available if info else False,
                embedding_loaded=info.loaded if info else False,
                embedding_provider=info.provider if info else None,
                embedding_model=info.model if info else None,
                dimension=info.dimension if info else None,
                index_count=self._current_index_count(project_id),
                last_error=f"{type(exc).__name__}: {exc}",
            )
            self.last_diagnostics = diagnostics
            self._project_diagnostics[project_id] = diagnostics
            raise
        info = self.embedding_provider.info() if self.embedding_provider else None
        diagnostics = RetrievalDiagnostics(
            effective_mode="hybrid" if info and info.loaded else "hybrid_pending",
            embedding_configured=True,
            embedding_available=info.available if info else True,
            embedding_loaded=info.loaded if info else True,
            embedding_provider=result.embedding_provider,
            embedding_model=result.embedding_model,
            dimension=result.dimension,
            index_count=result.index_count,
            last_error=info.last_error if info else None,
        )
        self.last_diagnostics = diagnostics
        self._project_diagnostics[project_id] = diagnostics
        return result

    def status(self, project_id: str | None = None) -> RetrievalDiagnostics:
        info = self.embedding_provider.info() if self.embedding_provider is not None else None
        base = (
            self._project_diagnostics.get(project_id, self._initial_diagnostics)
            if project_id is not None
            else self.last_diagnostics
        )
        effective_mode = base.effective_mode
        current_error = (
            (info.last_error if info else None)
            or base.last_error
        )
        if info is None:
            effective_mode = "lexical" if self.embedding_mode == "disabled" else "lexical_degraded"
        elif not info.available or current_error:
            effective_mode = "lexical_degraded"
        elif not info.loaded and base.effective_mode != "hybrid":
            effective_mode = "hybrid_pending"
        return replace(
            base,
            effective_mode=effective_mode,
            embedding_configured=self.embedding_provider is not None,
            embedding_available=info.available if info else False,
            embedding_loaded=info.loaded if info else False,
            embedding_provider=info.provider if info else None,
            embedding_model=info.model if info else None,
            dimension=info.dimension if info and info.dimension else base.dimension,
            index_count=self._current_index_count(project_id),
            last_error=current_error,
        )

    def _current_index_count(self, project_id: str | None) -> int:
        if self.embedding_provider is None:
            return 0
        return self.repository.count_vector_entries(
            project_id,
            embedding_provider=self.embedding_provider.provider_name,
            embedding_model=self.embedding_provider.model_name,
        )

    def _lexical_candidates(self, project_id: str, query: str, limit: int) -> list[ProjectRagCitation]:
        candidates: list[ProjectRagCitation] = []
        candidates.extend(self._fts_candidates(project_id, query, limit))
        candidates.extend(self._evidence_candidates(project_id, query))
        candidates.extend(self._document_candidates(project_id, query))
        candidates.extend(self._artifact_candidates(project_id, query))
        return candidates

    @staticmethod
    def _dedupe_lexical(candidates: list[ProjectRagCitation]) -> list[ProjectRagCitation]:
        deduped: dict[str, ProjectRagCitation] = {}
        for item in sorted(candidates, key=lambda citation: citation.score, reverse=True):
            deduped.setdefault(item.source_id, item)
        return list(deduped.values())

    def _fuse(
        self,
        lexical: list[ProjectRagCitation],
        vector: list[VectorCandidate],
        *,
        limit: int,
    ) -> list[ProjectRagCitation]:
        lexical_by_id = {item.source_id: (rank, item) for rank, item in enumerate(lexical, start=1)}
        vector_by_id = {item.source_id: (rank, item) for rank, item in enumerate(vector, start=1)}
        fused: list[ProjectRagCitation] = []
        ordered_source_ids = list(dict.fromkeys([
            *(item.source_id for item in lexical),
            *(item.source_id for item in vector),
        ]))
        for source_id in ordered_source_ids:
            lexical_entry = lexical_by_id.get(source_id)
            vector_entry = vector_by_id.get(source_id)
            lexical_rank = lexical_entry[0] if lexical_entry else None
            vector_rank = vector_entry[0] if vector_entry else None
            score = (
                (1.0 / (self.rrf_k + lexical_rank) if lexical_rank else 0.0)
                + (1.0 / (self.rrf_k + vector_rank) if vector_rank else 0.0)
            )
            if vector_entry is not None:
                vector_item = vector_entry[1]
                base = ProjectRagCitation(
                    source_id=vector_item.source_id,
                    source_type=vector_item.source_type,
                    title=vector_item.title,
                    snippet=_shorten(vector_item.text, 420),
                    score=score,
                    parent_id=vector_item.parent_id,
                    url=vector_item.url,
                    relative_path=vector_item.relative_path,
                    content_hash=vector_item.content_hash,
                    verification_status=vector_item.verification_status,
                    retrieval_mode="hybrid" if lexical_entry else "vector",
                    lexical_rank=lexical_rank,
                    vector_rank=vector_rank,
                    lexical_score=lexical_entry[1].score if lexical_entry else None,
                    vector_score=vector_item.similarity,
                    embedding_model=vector_item.embedding_model,
                )
            else:
                lexical_item = lexical_entry[1]
                base = replace(
                    lexical_item,
                    score=score,
                    retrieval_mode="lexical",
                    lexical_rank=lexical_rank,
                    lexical_score=lexical_item.score,
                )
            fused.append(base)
        return sorted(fused, key=lambda item: item.score, reverse=True)[: max(1, limit)]

    def _fts_candidates(self, project_id: str, query: str, limit: int) -> list[ProjectRagCitation]:
        try:
            results = self.repository.search_project(project_id, query, limit=limit)
        except Exception:
            return []
        evidence_by_id = {item.id: item for item in self.repository.list_evidence(project_id)}
        return [
            ProjectRagCitation(
                source_id=result.document_id,
                source_type="evidence",
                title=evidence_by_id[result.document_id].source_title if result.document_id in evidence_by_id else result.document_id,
                snippet=_shorten(result.snippet, 360),
                score=1.0 + result.score,
                url=evidence_by_id[result.document_id].source_url if result.document_id in evidence_by_id else None,
                verification_status=(
                    evidence_by_id[result.document_id].verification_status.value
                    if result.document_id in evidence_by_id else None
                ),
            )
            for result in results
        ]

    def _evidence_candidates(self, project_id: str, query: str) -> list[ProjectRagCitation]:
        candidates: list[ProjectRagCitation] = []
        for item in self.repository.list_evidence(project_id):
            text = " ".join([item.source_title, item.snippet, item.summary or ""])
            score = _score(query, text)
            if score <= 0:
                continue
            candidates.append(ProjectRagCitation(
                source_id=item.id,
                source_type="evidence",
                title=item.source_title,
                snippet=_shorten(item.summary or item.snippet or item.raw_excerpt or item.source_title, 360),
                score=score,
                url=item.source_url,
                verification_status=item.verification_status.value,
            ))
        return candidates

    def _document_candidates(self, project_id: str, query: str) -> list[ProjectRagCitation]:
        candidates: list[ProjectRagCitation] = []
        for document in self.repository.list_documents(project_id):
            segments = self.repository.list_document_segments(document.id)
            doc_score = _score(query, f"{document.file_name or ''}\n{document.content}")
            if not segments and doc_score > 0:
                candidates.append(ProjectRagCitation(
                    source_id=document.id,
                    source_type=f"document:{document.channel}",
                    title=document.file_name or document.id,
                    snippet=_shorten_around_query(document.content, query, 360),
                    score=doc_score * 0.9,
                    relative_path=document.file_name,
                ))
            for segment in segments:
                seg_score = _score(query, segment.text)
                if seg_score <= 0:
                    continue
                candidates.append(ProjectRagCitation(
                    source_id=segment.id,
                    source_type=f"document_segment:{document.channel}",
                    title=segment.heading or document.file_name or document.id,
                    snippet=_shorten_around_query(segment.text, query, 360),
                    score=seg_score,
                    parent_id=document.id,
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
    hits = sum(term in lowered for term in terms)
    return hits / len(terms)


def _terms(text: str) -> list[str]:
    lowered = text.lower()
    terms = re.findall(r"[a-z0-9_+#.-]{2,}", lowered)
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", lowered):
        terms.extend(sequence[index:index + 2] for index in range(len(sequence) - 1))
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
