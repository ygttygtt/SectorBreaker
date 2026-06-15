"""SQLite storage foundation."""

from __future__ import annotations

import sqlite3
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.app.providers.interfaces import RetrievalResult
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    EvidenceItem,
    MarketScope,
    ProjectStatus,
    ResearchDepth,
    ResearchProject,
    ResearchProjectCreate,
    VerificationStatus,
)

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def list_migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def init_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        for migration_file in list_migration_files():
            connection.executescript(migration_file.read_text(encoding="utf-8"))


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
            custom_market_scope=payload.custom_market_scope,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, title, domain, market_scope, depth, status,
                    custom_market_scope, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.title,
                    project.domain,
                    project.market_scope.value,
                    project.depth.value,
                    project.status.value,
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
        return ResearchProject(
            id=row["id"],
            title=row["title"],
            domain=row["domain"],
            market_scope=MarketScope(row["market_scope"]),
            depth=ResearchDepth(row["depth"]),
            status=ProjectStatus(row["status"]),
            custom_market_scope=row["custom_market_scope"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_projects(self) -> list[ResearchProject]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [
            ResearchProject(
                id=row["id"],
                title=row["title"],
                domain=row["domain"],
                market_scope=MarketScope(row["market_scope"]),
                depth=ResearchDepth(row["depth"]),
                status=ProjectStatus(row["status"]),
                custom_market_scope=row["custom_market_scope"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    def add_evidence(self, evidence: EvidenceItem) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence (
                    id, project_id, source_title, source_url, source_type,
                    snippet, summary, confidence, verification_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.id,
                    evidence.project_id,
                    evidence.source_title,
                    evidence.source_url,
                    evidence.source_type,
                    evidence.snippet,
                    evidence.summary,
                    evidence.confidence,
                    evidence.verification_status.value,
                ),
            )
            connection.execute(
                "INSERT INTO evidence_fts (id, project_id, content) VALUES (?, ?, ?)",
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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _row_to_evidence(row: sqlite3.Row) -> EvidenceItem:
        return EvidenceItem(
            id=row["id"],
            project_id=row["project_id"],
            source_title=row["source_title"],
            source_url=row["source_url"],
            source_type=row["source_type"],
            snippet=row["snippet"],
            summary=row["summary"],
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
    def _evidence_search_text(evidence: EvidenceItem) -> str:
        parts = [evidence.source_title, evidence.snippet, evidence.summary or ""]
        return "\n".join(part for part in parts if part)
