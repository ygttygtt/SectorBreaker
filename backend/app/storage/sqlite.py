"""SQLite storage foundation."""

from __future__ import annotations

import sqlite3
import json
from array import array
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from backend.app.documents import extract_document_citations, split_document_segments
from backend.app.providers.interfaces import RetrievalResult, VectorIndexEntry
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ClaimStrength,
    DocumentCitation,
    DocumentSegment,
    EvidenceClaim,
    EvidenceItem,
    MarketScope,
    ProjectMode,
    ProjectDocument,
    ProjectDocumentCreate,
    ProjectStatus,
    ResearchDepth,
    ResearchProject,
    ResearchProjectCreate,
    ProjectSourcePreferences,
    ResearchRun,
    RunEvent,
    RunStatus,
    SourceChannel,
    SourcePolicy,
    SourceQuality,
    UserInput,
    VerificationStatus,
    ChangeSet,
    KnowledgeHealthReport,
    MaintenanceTask,
    VaultImportRecord,
)

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def list_migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def init_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        for migration_file in list_migration_files():
            try:
                connection.executescript(migration_file.read_text(encoding="utf-8"))
            except sqlite3.OperationalError:
                pass  # idempotent: skip if already applied


class SQLiteRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def create_project(self, payload: ResearchProjectCreate) -> ResearchProject:
        now = datetime.now(UTC)
        project = ResearchProject(
            id=f"project-{uuid4().hex}",
            title=payload.title,
            domain=payload.domain,
            market_scope=payload.market_scope,
            depth=payload.depth,
            source_policy=payload.source_policy,
            project_mode=payload.project_mode,
            custom_market_scope=payload.custom_market_scope,
            source_preferences=payload.source_preferences,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, title, domain, market_scope, depth, status,
                    source_policy, project_mode, custom_market_scope,
                    source_preferences, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.title,
                    project.domain,
                    project.market_scope.value,
                    project.depth.value,
                    project.status.value,
                    project.source_policy.value,
                    project.project_mode.value,
                    project.custom_market_scope,
                    json.dumps(project.source_preferences.model_dump(mode="json"), ensure_ascii=False),
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
        return project

    def get_project(self, project_id: str) -> ResearchProject:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"project not found: {project_id}")
        return self._row_to_project(row)

    def list_projects(self) -> list[ResearchProject]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [self._row_to_project(row) for row in rows]

    def update_project_source_preferences(
        self,
        project_id: str,
        source_preferences: ProjectSourcePreferences,
    ) -> ResearchProject:
        now = datetime.now(UTC)
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE projects SET source_preferences = ?, updated_at = ? WHERE id = ?",
                (
                    json.dumps(source_preferences.model_dump(mode="json"), ensure_ascii=False),
                    now.isoformat(),
                    project_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"project not found: {project_id}")
        return self.get_project(project_id)

    def add_evidence(self, evidence: EvidenceItem) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO evidence (
                    id, project_id, source_title, source_url, source_type,
                    source_channel, source_policy, raw_excerpt, snippet, summary,
                    extraction_provider, extraction_metadata, collection_metadata, extracted_at,
                    claims, source_quality, claim_strength, bias_risk, recency,
                    corroborating_evidence_ids, conflicting_evidence_ids,
                    needs_counterevidence, collected_by, used_by_artifact_ids,
                    confidence, verification_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.id,
                    evidence.project_id,
                    evidence.source_title,
                    evidence.source_url,
                    evidence.source_type,
                    evidence.source_channel.value,
                    evidence.source_policy,
                    evidence.raw_excerpt,
                    evidence.snippet,
                    evidence.summary,
                    evidence.extraction_provider,
                    json.dumps(evidence.extraction_metadata, ensure_ascii=False),
                    json.dumps(evidence.collection_metadata, ensure_ascii=False),
                    evidence.extracted_at.isoformat() if evidence.extracted_at else None,
                    json.dumps([claim.model_dump(mode="json") for claim in evidence.claims], ensure_ascii=False),
                    evidence.source_quality.value,
                    evidence.claim_strength.value,
                    evidence.bias_risk,
                    evidence.recency,
                    json.dumps(evidence.corroborating_evidence_ids, ensure_ascii=False),
                    json.dumps(evidence.conflicting_evidence_ids, ensure_ascii=False),
                    1 if evidence.needs_counterevidence else 0,
                    evidence.collected_by,
                    json.dumps(evidence.used_by_artifact_ids, ensure_ascii=False),
                    evidence.confidence,
                    evidence.verification_status.value,
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO evidence_fts (id, project_id, content) VALUES (?, ?, ?)",
                (evidence.id, evidence.project_id, self._evidence_search_text(evidence)),
            )

    def list_evidence(self, project_id: str) -> list[EvidenceItem]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evidence WHERE project_id = ? ORDER BY rowid",
                (project_id,),
            ).fetchall()
        return [self._row_to_evidence(row) for row in rows]

    def add_artifact(self, artifact: Artifact) -> None:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM artifacts WHERE id = ?",
                (artifact.id,),
            ).fetchone()
            if existing is None and artifact.supersedes:
                predecessor = connection.execute(
                    "SELECT revision FROM artifacts WHERE id = ? AND project_id = ?",
                    (artifact.supersedes, artifact.project_id),
                ).fetchone()
                if predecessor is None:
                    raise ValueError(f"superseded artifact not found: {artifact.supersedes}")
                artifact.revision = int(predecessor["revision"] or 1) + 1
                connection.execute(
                    "UPDATE artifacts SET active = 0, superseded_by = ? WHERE id = ?",
                    (artifact.id, artifact.supersedes),
                )
            connection.execute(
                """
                INSERT OR REPLACE INTO artifacts (
                    id, project_id, artifact_type, title, content_path, content,
                    source_evidence_ids, schema_version, created_at, revision,
                    content_hash, active, supersedes, superseded_by, run_id,
                    change_set_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.id,
                    artifact.project_id,
                    artifact.artifact_type.value,
                    artifact.title,
                    artifact.content_path,
                    artifact.content,
                    json.dumps(artifact.source_evidence_ids, ensure_ascii=False),
                    artifact.schema_version,
                    artifact.created_at.isoformat(),
                    artifact.revision,
                    artifact.content_hash,
                    1 if artifact.active else 0,
                    artifact.supersedes,
                    artifact.superseded_by,
                    artifact.run_id,
                    artifact.change_set_id,
                ),
            )

    def list_artifacts(self, project_id: str, *, include_superseded: bool = False) -> list[Artifact]:
        with self._connect() as connection:
            if include_superseded:
                rows = connection.execute(
                    "SELECT * FROM artifacts WHERE project_id = ? ORDER BY content_path, revision",
                    (project_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM artifacts WHERE project_id = ? AND active = 1 ORDER BY content_path, revision",
                    (project_id,),
                ).fetchall()
        return [self._row_to_artifact(row) for row in rows]

    def get_artifact(self, artifact_id: str) -> Artifact:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if row is None:
            raise KeyError(f"artifact not found: {artifact_id}")
        return self._row_to_artifact(row)

    def list_artifact_history(self, project_id: str, content_path: str) -> list[Artifact]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE project_id = ? AND content_path = ? ORDER BY revision",
                (project_id, content_path),
            ).fetchall()
        return [self._row_to_artifact(row) for row in rows]

    def set_artifact_active(self, artifact_id: str, active: bool) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE artifacts SET active = ? WHERE id = ?",
                (1 if active else 0, artifact_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"artifact not found: {artifact_id}")

    def upsert_vector_entries(self, entries: list[VectorIndexEntry]) -> None:
        if not entries:
            return
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO vector_index (
                    chunk_id, project_id, source_id, parent_id, source_type,
                    title, relative_path, source_url, verification_status,
                    text_content, content_hash, embedding_provider,
                    embedding_model, dimension, vector, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.chunk_id,
                        item.project_id,
                        item.source_id,
                        item.parent_id,
                        item.source_type,
                        item.title,
                        item.relative_path,
                        item.url,
                        item.verification_status,
                        item.text,
                        item.content_hash,
                        item.embedding_provider,
                        item.embedding_model,
                        item.dimension,
                        array("f", item.vector).tobytes(),
                        item.indexed_at or now,
                    )
                    for item in entries
                ],
            )

    def sync_vector_snapshot(
        self,
        project_id: str,
        *,
        embedding_provider: str,
        embedding_model: str,
        entries: list[VectorIndexEntry],
        keep_chunk_ids: set[str],
        force: bool = False,
    ) -> int:
        """Atomically publish one project/model vector-index snapshot."""
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            existing_rows = connection.execute(
                """
                SELECT chunk_id FROM vector_index
                WHERE project_id = ? AND embedding_provider = ? AND embedding_model = ?
                """,
                (project_id, embedding_provider, embedding_model),
            ).fetchall()
            stale_ids = [row["chunk_id"] for row in existing_rows if row["chunk_id"] not in keep_chunk_ids]
            if force:
                connection.execute(
                    """
                    DELETE FROM vector_index
                    WHERE project_id = ? AND embedding_provider = ? AND embedding_model = ?
                    """,
                    (project_id, embedding_provider, embedding_model),
                )
            if entries:
                connection.executemany(
                    """
                    INSERT OR REPLACE INTO vector_index (
                        chunk_id, project_id, source_id, parent_id, source_type,
                        title, relative_path, source_url, verification_status,
                        text_content, content_hash, embedding_provider,
                        embedding_model, dimension, vector, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item.chunk_id,
                            item.project_id,
                            item.source_id,
                            item.parent_id,
                            item.source_type,
                            item.title,
                            item.relative_path,
                            item.url,
                            item.verification_status,
                            item.text,
                            item.content_hash,
                            item.embedding_provider,
                            item.embedding_model,
                            item.dimension,
                            array("f", item.vector).tobytes(),
                            item.indexed_at or now,
                        )
                        for item in entries
                    ],
                )
            if stale_ids and not force:
                connection.executemany(
                    """
                    DELETE FROM vector_index
                    WHERE chunk_id = ? AND project_id = ?
                      AND embedding_provider = ? AND embedding_model = ?
                    """,
                    [
                        (chunk_id, project_id, embedding_provider, embedding_model)
                        for chunk_id in stale_ids
                    ],
                )
        return len(stale_ids)

    def list_vector_entries(
        self,
        project_id: str,
        *,
        embedding_provider: str,
        embedding_model: str,
    ) -> list[VectorIndexEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM vector_index
                WHERE project_id = ? AND embedding_provider = ? AND embedding_model = ?
                ORDER BY chunk_id
                """,
                (project_id, embedding_provider, embedding_model),
            ).fetchall()
        return [self._row_to_vector_entry(row) for row in rows]

    def delete_stale_vector_entries(
        self,
        project_id: str,
        *,
        embedding_provider: str,
        embedding_model: str,
        keep_chunk_ids: set[str],
    ) -> int:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id FROM vector_index
                WHERE project_id = ? AND embedding_provider = ? AND embedding_model = ?
                """,
                (project_id, embedding_provider, embedding_model),
            ).fetchall()
            stale_ids = [row["chunk_id"] for row in rows if row["chunk_id"] not in keep_chunk_ids]
            if stale_ids:
                connection.executemany(
                    """
                    DELETE FROM vector_index
                    WHERE chunk_id = ? AND project_id = ?
                      AND embedding_provider = ? AND embedding_model = ?
                    """,
                    [
                        (chunk_id, project_id, embedding_provider, embedding_model)
                        for chunk_id in stale_ids
                    ],
                )
        return len(stale_ids)

    def clear_vector_index(self, project_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM vector_index WHERE project_id = ?", (project_id,))
        return max(cursor.rowcount, 0)

    def count_vector_entries(
        self,
        project_id: str | None = None,
        *,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
    ) -> int:
        clauses: list[str] = []
        parameters: list[str] = []
        if project_id is not None:
            clauses.append("project_id = ?")
            parameters.append(project_id)
        if embedding_provider is not None:
            clauses.append("embedding_provider = ?")
            parameters.append(embedding_provider)
        if embedding_model is not None:
            clauses.append("embedding_model = ?")
            parameters.append(embedding_model)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS count FROM vector_index{where}",  # noqa: S608 - fixed clauses only
                parameters,
            ).fetchone()
        return int(row["count"] if row else 0)

    def save_vault_import(self, record: VaultImportRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO vault_imports (
                    id, project_id, source_path, note_count, total_bytes,
                    snapshot_hash, imported_paths, skipped_paths, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.project_id,
                    record.source_path,
                    record.note_count,
                    record.total_bytes,
                    record.snapshot_hash,
                    json.dumps(record.imported_paths, ensure_ascii=False),
                    json.dumps(record.skipped_paths, ensure_ascii=False),
                    record.created_at.isoformat(),
                ),
            )

    def latest_vault_import(self, project_id: str) -> VaultImportRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM vault_imports WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return VaultImportRecord(
            id=row["id"],
            project_id=row["project_id"],
            source_path=row["source_path"],
            note_count=row["note_count"],
            total_bytes=row["total_bytes"],
            snapshot_hash=row["snapshot_hash"],
            imported_paths=json.loads(row["imported_paths"] or "[]"),
            skipped_paths=json.loads(row["skipped_paths"] or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def save_health_report(self, report: KnowledgeHealthReport) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO knowledge_health_reports (
                    id, project_id, vault_import_id, snapshot_hash, report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    report.project_id,
                    report.vault_import_id,
                    report.snapshot_hash,
                    report.model_dump_json(),
                    report.generated_at.isoformat(),
                ),
            )

    def latest_health_report(self, project_id: str) -> KnowledgeHealthReport | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT report_json FROM knowledge_health_reports WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return KnowledgeHealthReport.model_validate_json(row["report_json"]) if row else None

    def upsert_maintenance_task(self, task: MaintenanceTask) -> MaintenanceTask:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT task_json FROM maintenance_tasks WHERE project_id = ? AND fingerprint = ?",
                (task.project_id, task.fingerprint),
            ).fetchone()
            if row is not None:
                existing = MaintenanceTask.model_validate_json(row["task_json"])
                if existing.status.value not in {"done", "dismissed"}:
                    return existing
            connection.execute(
                """
                INSERT OR REPLACE INTO maintenance_tasks (
                    id, project_id, fingerprint, status, task_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.project_id,
                    task.fingerprint,
                    task.status.value,
                    task.model_dump_json(),
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )
        return task

    def list_maintenance_tasks(self, project_id: str) -> list[MaintenanceTask]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_json FROM maintenance_tasks WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        return [MaintenanceTask.model_validate_json(row["task_json"]) for row in rows]

    def save_maintenance_task(self, task: MaintenanceTask) -> None:
        task.updated_at = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE maintenance_tasks
                SET status = ?, task_json = ?, updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (task.status.value, task.model_dump_json(), task.updated_at.isoformat(), task.id, task.project_id),
            )

    def save_change_set(self, change_set: ChangeSet) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO change_sets (
                    id, project_id, task_id, status, change_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change_set.id,
                    change_set.project_id,
                    change_set.task_id,
                    change_set.status.value,
                    change_set.model_dump_json(),
                    change_set.created_at.isoformat(),
                    now,
                ),
            )

    def get_change_set(self, change_set_id: str) -> ChangeSet:
        with self._connect() as connection:
            row = connection.execute("SELECT change_json FROM change_sets WHERE id = ?", (change_set_id,)).fetchone()
        if row is None:
            raise KeyError(f"change set not found: {change_set_id}")
        return ChangeSet.model_validate_json(row["change_json"])

    def list_change_sets(self, project_id: str) -> list[ChangeSet]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT change_json FROM change_sets WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [ChangeSet.model_validate_json(row["change_json"]) for row in rows]

    def search_project(self, project_id: str, query: str, limit: int) -> list[RetrievalResult]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, content
                FROM evidence_fts
                WHERE evidence_fts MATCH ? AND project_id = ?
                LIMIT ?
                """,
                (query, project_id, limit),
            ).fetchall()
        return [
            RetrievalResult(document_id=row["id"], snippet=row["content"], score=1.0)
            for row in rows
        ]

    def add_document(self, project_id: str, payload: ProjectDocumentCreate, document_id: str | None = None) -> ProjectDocument:
        now = datetime.now(UTC)
        content = payload.content
        generated_document_id = document_id or f"doc-{uuid4().hex}"
        segments = split_document_segments(generated_document_id, content)
        citations = extract_document_citations(generated_document_id, segments)
        document = ProjectDocument(
            id=generated_document_id,
            project_id=project_id,
            channel=payload.channel,
            file_name=payload.file_name,
            mime_type=payload.mime_type,
            content=content,
            word_count=len(content.split()),
            char_count=len(content),
            segment_count=len(segments),
            citation_count=len(citations),
            created_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, project_id, channel, file_name, mime_type, content,
                    word_count, char_count, segment_count, citation_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.id,
                    document.project_id,
                    document.channel,
                    document.file_name,
                    document.mime_type,
                    document.content,
                    document.word_count,
                    document.char_count,
                    document.segment_count,
                    document.citation_count,
                    document.created_at.isoformat(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO document_segments (
                    id, document_id, order_index, heading, text, char_count, citation_refs
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        segment.id,
                        segment.document_id,
                        segment.order_index,
                        segment.heading,
                        segment.text,
                        segment.char_count,
                        json.dumps(segment.citation_refs, ensure_ascii=False),
                    )
                    for segment in segments
                ],
            )
            connection.executemany(
                """
                INSERT INTO document_citations (
                    id, document_id, raw_reference, source_title, source_url, referenced_segment_ids
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        citation.id,
                        citation.document_id,
                        citation.raw_reference,
                        citation.source_title,
                        citation.source_url,
                        json.dumps(citation.referenced_segment_ids, ensure_ascii=False),
                    )
                    for citation in citations
                ],
            )
        return document

    def list_documents(self, project_id: str) -> list[ProjectDocument]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM documents WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [self._row_to_document(row) for row in rows]

    def get_document(self, document_id: str) -> ProjectDocument:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            raise KeyError(f"document not found: {document_id}")
        return self._row_to_document(row)

    def list_document_segments(self, document_id: str) -> list[DocumentSegment]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM document_segments WHERE document_id = ? ORDER BY order_index",
                (document_id,),
            ).fetchall()
        return [
            DocumentSegment(
                id=row["id"],
                document_id=row["document_id"],
                order_index=row["order_index"],
                heading=row["heading"],
                text=row["text"],
                char_count=row["char_count"],
                citation_refs=json.loads(row["citation_refs"] or "[]"),
            )
            for row in rows
        ]

    def list_document_citations(self, document_id: str) -> list[DocumentCitation]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM document_citations WHERE document_id = ? ORDER BY id",
                (document_id,),
            ).fetchall()
        return [
            DocumentCitation(
                id=row["id"],
                document_id=row["document_id"],
                raw_reference=row["raw_reference"],
                source_title=row["source_title"],
                source_url=row["source_url"],
                referenced_segment_ids=json.loads(row["referenced_segment_ids"] or "[]"),
            )
            for row in rows
        ]

    def list_evidence_by_collector(self, project_id: str, collected_by: str) -> list[EvidenceItem]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evidence WHERE project_id = ? AND collected_by = ? ORDER BY rowid",
                (project_id, collected_by),
            ).fetchall()
        return [self._row_to_evidence(row) for row in rows]

    def get_evidence(self, evidence_id: str) -> EvidenceItem:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone()
        if row is None:
            raise KeyError(f"evidence not found: {evidence_id}")
        return self._row_to_evidence(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _row_to_vector_entry(row: sqlite3.Row) -> VectorIndexEntry:
        vector = array("f")
        vector.frombytes(bytes(row["vector"]))
        return VectorIndexEntry(
            chunk_id=row["chunk_id"],
            project_id=row["project_id"],
            source_id=row["source_id"],
            parent_id=row["parent_id"],
            source_type=row["source_type"],
            title=row["title"],
            text=row["text_content"],
            content_hash=row["content_hash"],
            embedding_provider=row["embedding_provider"],
            embedding_model=row["embedding_model"],
            dimension=row["dimension"],
            vector=tuple(float(value) for value in vector),
            relative_path=row["relative_path"],
            url=row["source_url"],
            verification_status=row["verification_status"],
            indexed_at=row["indexed_at"],
        )

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> ResearchProject:
        row_keys = set(row.keys())
        return ResearchProject(
            id=row["id"],
            title=row["title"],
            domain=row["domain"],
            market_scope=MarketScope(row["market_scope"]),
            depth=ResearchDepth(row["depth"]),
            source_policy=SourcePolicy(row["source_policy"] or SourcePolicy.RELIABLE_FIRST.value),
            project_mode=ProjectMode(
                row["project_mode"] if "project_mode" in row_keys and row["project_mode"] else ProjectMode.DOMAIN_KNOWLEDGE.value
            ),
            status=ProjectStatus(row["status"]),
            custom_market_scope=row["custom_market_scope"],
            source_preferences=ProjectSourcePreferences.model_validate_json(
                row["source_preferences"]
                if "source_preferences" in row_keys and row["source_preferences"]
                else "{}"
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_evidence(row: sqlite3.Row) -> EvidenceItem:
        return EvidenceItem(
            id=row["id"],
            project_id=row["project_id"],
            source_title=row["source_title"],
            source_url=row["source_url"],
            source_type=row["source_type"],
            source_channel=SourceChannel(row["source_channel"] or SourceChannel.SEARCH.value),
            source_policy=row["source_policy"],
            raw_excerpt=row["raw_excerpt"],
            snippet=row["snippet"],
            summary=row["summary"],
            extraction_provider=row["extraction_provider"] if "extraction_provider" in row.keys() else None,
            extraction_metadata=(
                json.loads(row["extraction_metadata"])
                if "extraction_metadata" in row.keys() and row["extraction_metadata"]
                else {}
            ),
            collection_metadata=(
                json.loads(row["collection_metadata"])
                if "collection_metadata" in row.keys() and row["collection_metadata"]
                else {}
            ),
            extracted_at=(
                datetime.fromisoformat(row["extracted_at"])
                if "extracted_at" in row.keys() and row["extracted_at"]
                else None
            ),
            claims=[EvidenceClaim(**item) for item in json.loads(row["claims"] or "[]")],
            source_quality=SourceQuality(row["source_quality"] or SourceQuality.UNKNOWN.value),
            claim_strength=ClaimStrength(row["claim_strength"] or ClaimStrength.OPINION.value),
            bias_risk=row["bias_risk"],
            recency=row["recency"],
            corroborating_evidence_ids=json.loads(row["corroborating_evidence_ids"] or "[]"),
            conflicting_evidence_ids=json.loads(row["conflicting_evidence_ids"] or "[]"),
            needs_counterevidence=bool(row["needs_counterevidence"]),
            collected_by=row["collected_by"],
            used_by_artifact_ids=json.loads(row["used_by_artifact_ids"] or "[]"),
            confidence=row["confidence"],
            verification_status=VerificationStatus(row["verification_status"]),
        )

    @staticmethod
    def _row_to_artifact(row: sqlite3.Row) -> Artifact:
        row_keys = set(row.keys())
        return Artifact(
            id=row["id"],
            project_id=row["project_id"],
            artifact_type=ArtifactType(row["artifact_type"]),
            title=row["title"],
            content_path=row["content_path"],
            content=row["content"],
            source_evidence_ids=json.loads(row["source_evidence_ids"]),
            schema_version=row["schema_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            revision=int(row["revision"] or 1) if "revision" in row_keys else 1,
            content_hash=row["content_hash"] if "content_hash" in row_keys else "",
            active=bool(row["active"]) if "active" in row_keys else True,
            supersedes=row["supersedes"] if "supersedes" in row_keys else None,
            superseded_by=row["superseded_by"] if "superseded_by" in row_keys else None,
            run_id=row["run_id"] if "run_id" in row_keys else None,
            change_set_id=row["change_set_id"] if "change_set_id" in row_keys else None,
        )

    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> ProjectDocument:
        return ProjectDocument(
            id=row["id"],
            project_id=row["project_id"],
            channel=row["channel"],
            file_name=row["file_name"],
            mime_type=row["mime_type"],
            content=row["content"],
            word_count=row["word_count"],
            char_count=row["char_count"],
            segment_count=row["segment_count"],
            citation_count=row["citation_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _evidence_search_text(evidence: EvidenceItem) -> str:
        parts = [evidence.source_title, evidence.snippet, evidence.summary or ""]
        return "\n".join(part for part in parts if part)

    # ── Runs ──────────────────────────────────────────────────────

    def create_run(
        self,
        project_id: str,
        run_id: str | None = None,
        *,
        resumed_from_run_id: str | None = None,
    ) -> ResearchRun:
        now = datetime.now(UTC)
        run = ResearchRun(
            id=run_id or f"run-{uuid4().hex}",
            project_id=project_id,
            status=RunStatus.PENDING,
            resumed_from_run_id=resumed_from_run_id,
            created_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs (id, project_id, status, resumed_from_run_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (run.id, run.project_id, run.status.value, resumed_from_run_id, run.created_at.isoformat()),
            )
        return run

    def create_claimed_run(
        self,
        project_id: str,
        *,
        lease_owner_id: str,
        lease_seconds: int,
        resumed_from_run_id: str | None = None,
    ) -> ResearchRun:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=lease_seconds)
        run_id = f"run-{uuid4().hex}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._reconcile_stale_runs(connection, now)
            active = connection.execute(
                """
                SELECT id FROM runs
                WHERE project_id = ? AND status IN (?, ?, ?)
                LIMIT 1
                """,
                (
                    project_id,
                    RunStatus.PENDING.value,
                    RunStatus.RUNNING.value,
                    RunStatus.WAITING_FOR_HUMAN.value,
                ),
            ).fetchone()
            if active is not None:
                raise ValueError(f"project already has an active run: {active['id']}")
            try:
                connection.execute(
                    """
                    INSERT INTO runs (
                        id, project_id, status, heartbeat_at, lease_owner_id,
                        lease_expires_at, resumed_from_run_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        project_id,
                        RunStatus.RUNNING.value,
                        now.isoformat(),
                        lease_owner_id,
                        expires_at.isoformat(),
                        resumed_from_run_id,
                        now.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("run recovery already exists") from exc
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> ResearchRun:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"run not found: {run_id}")
        return self._row_to_run(row)

    def get_active_run(self, project_id: str) -> ResearchRun | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM runs
                WHERE project_id = ? AND status IN (?, ?, ?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    project_id,
                    RunStatus.PENDING.value,
                    RunStatus.RUNNING.value,
                    RunStatus.WAITING_FOR_HUMAN.value,
                ),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    def get_latest_run(self, project_id: str) -> ResearchRun | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM runs
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> ResearchRun:
        return ResearchRun(
            id=row["id"],
            project_id=row["project_id"],
            status=RunStatus(row["status"]),
            current_gate=row["current_gate"],
            current_step=row["current_step"],
            workflow_state=row["workflow_state"],
            heartbeat_at=datetime.fromisoformat(row["heartbeat_at"]) if row["heartbeat_at"] else None,
            lease_owner_id=row["lease_owner_id"],
            lease_expires_at=datetime.fromisoformat(row["lease_expires_at"]) if row["lease_expires_at"] else None,
            terminal_reason=row["terminal_reason"],
            resumed_from_run_id=row["resumed_from_run_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )

    def update_run(
        self,
        run_id: str,
        status: RunStatus | None = None,
        current_gate: str | None = None,
        current_step: str | None = None,
        completed_at: datetime | None = None,
        workflow_state: str | None = None,
        terminal_reason: str | None = None,
    ) -> None:
        sets = []
        params: list[object] = []
        if status is not None:
            sets.append("status = ?")
            params.append(status.value)
        if current_gate is not None:
            sets.append("current_gate = ?")
            params.append(current_gate)
        if current_step is not None:
            sets.append("current_step = ?")
            params.append(current_step)
        if completed_at is not None:
            sets.append("completed_at = ?")
            params.append(completed_at.isoformat())
        if workflow_state is not None:
            sets.append("workflow_state = ?")
            params.append(workflow_state)
        if terminal_reason is not None:
            sets.append("terminal_reason = ?")
            params.append(terminal_reason)
        if not sets:
            return
        params.append(run_id)
        with self._connect() as connection:
            connection.execute(f"UPDATE runs SET {', '.join(sets)} WHERE id = ?", params)

    def claim_waiting_run(self, run_id: str, *, lease_owner_id: str, lease_seconds: int) -> bool:
        now = datetime.now(UTC)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runs
                SET status = ?, heartbeat_at = ?, lease_owner_id = ?,
                    lease_expires_at = ?, terminal_reason = NULL, completed_at = NULL
                WHERE id = ? AND status = ?
                """,
                (
                    RunStatus.RUNNING.value,
                    now.isoformat(),
                    lease_owner_id,
                    (now + timedelta(seconds=lease_seconds)).isoformat(),
                    run_id,
                    RunStatus.WAITING_FOR_HUMAN.value,
                ),
            )
            return cursor.rowcount == 1

    def finish_owned_run(
        self,
        run_id: str,
        *,
        lease_owner_id: str,
        status: RunStatus,
        current_gate: str,
        terminal_reason: str | None = None,
    ) -> None:
        completed_at = datetime.now(UTC) if status in {RunStatus.COMPLETED, RunStatus.FAILED} else None
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runs
                SET status = ?, current_gate = ?, completed_at = ?,
                    terminal_reason = ?, lease_owner_id = NULL, lease_expires_at = NULL
                WHERE id = ? AND status = ? AND lease_owner_id = ?
                  AND lease_expires_at > ?
                """,
                (
                    status.value,
                    current_gate,
                    completed_at.isoformat() if completed_at else None,
                    terminal_reason,
                    run_id,
                    RunStatus.RUNNING.value,
                    lease_owner_id,
                    datetime.now(UTC).isoformat(),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("run lease lost before finalization")

    def reconcile_stale_runs(self, now: datetime | None = None) -> list[ResearchRun]:
        effective_now = now or datetime.now(UTC)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run_ids = self._reconcile_stale_runs(connection, effective_now)
        return [self.get_run(run_id) for run_id in run_ids]

    @staticmethod
    def _reconcile_stale_runs(connection: sqlite3.Connection, now: datetime) -> list[str]:
        rows = connection.execute(
            """
            SELECT id FROM runs
            WHERE status IN (?, ?)
              AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
            """,
            (RunStatus.PENDING.value, RunStatus.RUNNING.value, now.isoformat()),
        ).fetchall()
        reconciled: list[str] = []
        for row in rows:
            run_id = row["id"]
            checkpoint = connection.execute(
                "SELECT 1 FROM run_state_checkpoints WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
            status = RunStatus.INTERRUPTED if checkpoint is not None else RunStatus.FAILED
            reason = "lease_expired" if checkpoint is not None else "orphaned_no_checkpoint"
            connection.execute(
                """
                UPDATE runs
                SET status = ?, terminal_reason = ?, lease_owner_id = NULL,
                    lease_expires_at = NULL, completed_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    reason,
                    now.isoformat() if status == RunStatus.FAILED else None,
                    run_id,
                ),
            )
            reconciled.append(run_id)
        return reconciled

    def has_run_state_checkpoint(self, run_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM run_state_checkpoints WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
        return row is not None

    def has_recovery_child(self, run_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM runs WHERE resumed_from_run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
        return row is not None

    # ── Run Events ────────────────────────────────────────────────

    def add_run_event(
        self,
        event: RunEvent,
        run_id: str,
        *,
        lease_owner_id: str | None = None,
        lease_seconds: int = 90,
    ) -> int:
        with self._connect() as connection:
            if lease_owner_id is not None:
                now = datetime.now(UTC)
                lease_cursor = connection.execute(
                    """
                    UPDATE runs
                    SET heartbeat_at = ?, lease_expires_at = ?, current_gate = ?, current_step = ?
                    WHERE id = ? AND status = ? AND lease_owner_id = ?
                      AND lease_expires_at > ?
                    """,
                    (
                        now.isoformat(),
                        (now + timedelta(seconds=lease_seconds)).isoformat(),
                        event.gate,
                        event.step,
                        run_id,
                        RunStatus.RUNNING.value,
                        lease_owner_id,
                        now.isoformat(),
                    ),
                )
                if lease_cursor.rowcount != 1:
                    raise RuntimeError("run lease lost before event append")
            cursor = connection.execute(
                """
                INSERT INTO run_events (
                    run_id, event_type, gate, step, agent, message, data,
                    progress_current, progress_total, severity, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event.event_type,
                    event.gate,
                    event.step,
                    event.agent,
                    event.message,
                    json.dumps(event.data, ensure_ascii=False) if event.data else None,
                    event.progress_current,
                    event.progress_total,
                    event.severity,
                    datetime.fromtimestamp(event.timestamp, tz=UTC).isoformat(),
                ),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def list_run_events(self, run_id: str, after_id: int = 0) -> list[RunEvent]:
        return [event for _, event in self.list_run_event_records(run_id, after_id=after_id)]

    def list_run_event_records(self, run_id: str, after_id: int = 0) -> list[tuple[int, RunEvent]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM run_events WHERE run_id = ? AND id > ? ORDER BY id",
                (run_id, after_id),
            ).fetchall()
        return [
            (
                row["id"],
                RunEvent(
                    event_type=row["event_type"],
                    gate=row["gate"],
                    step=row["step"],
                    agent=row["agent"],
                    message=row["message"],
                    data=json.loads(row["data"]) if row["data"] else None,
                    progress_current=row["progress_current"],
                    progress_total=row["progress_total"],
                    severity=row["severity"] or "info",
                    timestamp=datetime.fromisoformat(row["created_at"]).timestamp(),
                ),
            )
            for row in rows
        ]

    # ── User Inputs ───────────────────────────────────────────────

    def add_user_input(self, user_input: UserInput) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO user_inputs (id, run_id, gate, input_type, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_input.id,
                    user_input.run_id,
                    user_input.gate,
                    user_input.input_type,
                    user_input.content,
                    user_input.created_at.isoformat(),
                ),
            )

    # ── Run State Checkpoints ─────────────────────────────────────

    def save_run_state_checkpoint(
        self,
        *,
        run_id: str,
        project_id: str,
        state: "SectorBreakerState",  # type: ignore[name-defined]
        checkpoint_type: str = "artifact_write",
        artifact_id: str | None = None,
        iteration: int = 0,
    ) -> None:
        """Persist the full SectorBreakerState as a JSON checkpoint for later resume."""
        checkpoint_id = f"ckpt-{uuid4().hex}"
        state_json = state.model_dump_json()
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_state_checkpoints
                    (id, run_id, project_id, state_json, checkpoint_type, artifact_id, iteration, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (checkpoint_id, run_id, project_id, state_json, checkpoint_type, artifact_id, iteration, now),
            )

    def load_run_state_checkpoint(self, *, run_id: str) -> "SectorBreakerState | None":  # type: ignore[name-defined]
        """Load the most recent checkpoint for a run. Returns None if none exists."""
        from backend.app.agent_state.models import SectorBreakerState
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json FROM run_state_checkpoints
                WHERE run_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return SectorBreakerState.model_validate_json(row[0])

    def load_latest_resumable_project_checkpoint(self, *, project_id: str) -> "SectorBreakerState | None":  # type: ignore[name-defined]
        """Load the newest project checkpoint that is safe to use for continuation."""
        from backend.app.agent_state.models import SectorBreakerState
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state_json FROM run_state_checkpoints
                WHERE project_id = ?
                  AND checkpoint_type IN ('artifact_write', 'run_end_completed')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return SectorBreakerState.model_validate_json(row[0])
