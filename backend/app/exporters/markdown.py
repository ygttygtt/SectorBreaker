"""Markdown and Obsidian-compatible export writer."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from backend.app.schemas import Artifact, EvidenceItem, ResearchProject


class ExportManifest(BaseModel):
    export_version: str
    project_id: str
    generated_at: datetime
    artifact_paths: list[str]
    evidence_ids: list[str]


class MarkdownExporter:
    def __init__(self, export_root: Path) -> None:
        self.export_root = export_root

    def export_project(
        self,
        project: ResearchProject,
        artifacts: list[Artifact],
        evidence: list[EvidenceItem],
    ) -> ExportManifest:
        project_dir = self.export_root / self._slugify(project.title)
        project_dir.mkdir(parents=True, exist_ok=True)

        artifact_paths: list[str] = []
        for artifact in artifacts:
            relative_path = Path(artifact.content_path)
            output_path = project_dir / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(self._render_artifact(project, artifact), encoding="utf-8")
            artifact_paths.append(relative_path.as_posix())

        manifest = ExportManifest(
            export_version="1",
            project_id=project.id,
            generated_at=datetime.now(UTC),
            artifact_paths=artifact_paths,
            evidence_ids=[item.id for item in evidence],
        )
        (project_dir / "manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    @staticmethod
    def _render_artifact(project: ResearchProject, artifact: Artifact) -> str:
        evidence_ids = ", ".join(artifact.source_evidence_ids)
        return (
            "---\n"
            f'project: "{project.title}"\n'
            f'artifact_type: "{artifact.artifact_type.value}"\n'
            f'schema_version: "{artifact.schema_version}"\n'
            f"evidence_ids: [{evidence_ids}]\n"
            "---\n\n"
            f"{artifact.content}\n"
        )

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
        return slug or "sectorbreaker-project"
