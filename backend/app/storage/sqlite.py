"""SQLite storage foundation."""

from __future__ import annotations

import sqlite3
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.app.documents import extract_document_citations, split_document_segments
from backend.app.providers.interfaces import RetrievalResult
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
    ResearchRun,
    RunEvent,
    RunStatus,
    SourceChannel,
    SourcePolicy,
    SourceQuality,
    UserInput,
    VerificationStatus,
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
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, title, domain, market_scope, depth, status,
                    source_policy, project_mode, custom_market_scope, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    def add_evidence(self, evidence: EvidenceItem) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO evidence (
                    id, project_id, source_title, source_url, source_type,
                    source_channel, source_policy, raw_excerpt, snippet, summary,
                    claims, source_quality, claim_strength, bias_risk, recency,
                    corroborating_evidence_ids, conflicting_evidence_ids,
                    needs_counterevidence, collected_by, used_by_artifact_ids,
                    confidence, verification_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            connection.execute(
                """
                INSERT OR REPLACE INTO artifacts (
                    id, project_id, artifact_type, title, content_path, content,
                    source_evidence_ids, schema_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )

    def list_artifacts(self, project_id: str) -> list[Artifact]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
        return [self._row_to_artifact(row) for row in rows]

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

    def create_run(self, project_id: str, run_id: str | None = None) -> ResearchRun:
        now = datetime.now(UTC)
        run = ResearchRun(
            id=run_id or f"run-{uuid4().hex}",
            project_id=project_id,
            status=RunStatus.PENDING,
            created_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs (id, project_id, status, created_at) VALUES (?, ?, ?, ?)",
                (run.id, run.project_id, run.status.value, run.created_at.isoformat()),
            )
        return run

    def get_run(self, run_id: str) -> ResearchRun:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"run not found: {run_id}")
        return ResearchRun(
            id=row["id"],
            project_id=row["project_id"],
            status=RunStatus(row["status"]),
            current_gate=row["current_gate"],
            current_step=row["current_step"],
            workflow_state=row["workflow_state"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )

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
        return ResearchRun(
            id=row["id"],
            project_id=row["project_id"],
            status=RunStatus(row["status"]),
            current_gate=row["current_gate"],
            current_step=row["current_step"],
            workflow_state=row["workflow_state"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )

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
        return ResearchRun(
            id=row["id"],
            project_id=row["project_id"],
            status=RunStatus(row["status"]),
            current_gate=row["current_gate"],
            current_step=row["current_step"],
            workflow_state=row["workflow_state"],
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
        if not sets:
            return
        params.append(run_id)
        with self._connect() as connection:
            connection.execute(f"UPDATE runs SET {', '.join(sets)} WHERE id = ?", params)

    # ── Run Events ────────────────────────────────────────────────

    def add_run_event(self, event: RunEvent, run_id: str) -> int:
        with self._connect() as connection:
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
