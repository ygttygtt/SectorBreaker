"""Markdown and Obsidian-compatible export writer.

Exports are organized by the 5 steps from the design doc:
01-建立行业数据库, 02-反向拆解, 03-内容生态, 04-知识地图, 05-学习路径
"""

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

        # Write each artifact to its content_path
        for artifact in artifacts:
            relative_path = Path(artifact.content_path)
            output_path = project_dir / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(self._render_artifact(project, artifact), encoding="utf-8")
            artifact_paths.append(relative_path.as_posix())

        # Generate evidence index
        evidence_path = self._generate_evidence_index(project, evidence, project_dir)
        if evidence_path:
            artifact_paths.append(evidence_path)

        # Generate project README
        readme_path = self._generate_readme(project, artifacts, evidence, project_dir)
        if readme_path:
            artifact_paths.append(readme_path)

        # Generate learning path
        learning_path = self._generate_learning_path(project, artifacts, project_dir)
        if learning_path:
            artifact_paths.append(learning_path)

        # Write manifest
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

    def _generate_readme(
        self, project: ResearchProject, artifacts: list[Artifact],
        evidence: list[EvidenceItem], project_dir: Path,
    ) -> str | None:
        """Generate project README with navigation."""
        lines = [
            "---",
            f'project: "{project.title}"',
            f"generated_at: \"{datetime.now(UTC).strftime('%Y-%m-%d')}\"",
            "---\n",
            f"# {project.title}\n",
            f"**领域**：{project.domain} | **市场范围**：{project.market_scope.value} | **深度**：{project.depth.value}\n",
        ]

        # Group artifacts by directory
        groups: dict[str, list[Artifact]] = {}
        for art in artifacts:
            parts = Path(art.content_path).parts
            group = parts[0] if len(parts) > 1 else "其他"
            groups.setdefault(group, []).append(art)

        # Navigation by step
        step_order = [
            ("01-建立行业数据库", "第一步：建立行业数据库"),
            ("02-市场分析", "第一步续：市场分析"),
            ("03-玩家与竞品", "第二步：反向拆解"),
            ("04-内容生态", "第三步：内容生态"),
            ("05-机会与验证", "第四步：机会地图"),
            ("06-知识卡片模板", "知识卡片模板"),
        ]

        for dir_prefix, label in step_order:
            matching = [g for g in groups if g.startswith(dir_prefix.split("-")[0])]
            if matching:
                lines.append(f"## {label}\n")
                for g in sorted(matching):
                    for art in groups.get(g, []):
                        path = art.content_path
                        title = art.title or Path(path).stem
                        lines.append(f"- [[{Path(path).stem}]] — {title}")
                lines.append("")

        # Other artifacts
        other = [g for g in groups if not any(g.startswith(s.split("-")[0]) for _, s in step_order)]
        if other:
            lines.append("## 其他\n")
            for g in sorted(other):
                for art in groups.get(g, []):
                    lines.append(f"- [[{Path(art.content_path).stem}]]")

        lines.append(f"\n**证据数量**：{len(evidence)} | **产物数量**：{len(artifacts)}")

        readme_path = project_dir / "README.md"
        readme_path.write_text("\n".join(lines), encoding="utf-8")
        return "README.md"

    def _generate_evidence_index(
        self, project: ResearchProject, evidence: list[EvidenceItem], project_dir: Path,
    ) -> str | None:
        """Generate evidence index file."""
        if not evidence:
            return None

        lines = [
            "---",
            f'project: "{project.title}"',
            'type: "evidence_index"',
            "---\n",
            f"# {project.title} 证据库\n",
        ]

        for ev in evidence:
            source = ev.source_title or ev.id
            url_part = f" — [链接]({ev.source_url})" if ev.source_url else ""
            confidence = f" (可信度: {ev.confidence})" if ev.confidence else ""
            status = f" [{ev.verification_status.value}]" if ev.verification_status else ""
            lines.append(f"### {ev.id}{status}\n")
            lines.append(f"**来源**：{source}{url_part}{confidence}\n")
            if ev.snippet:
                lines.append(f"> {ev.snippet[:200]}\n")
            lines.append("")

        evidence_path = project_dir / "证据库.md"
        evidence_path.write_text("\n".join(lines), encoding="utf-8")
        return "证据库.md"

    def _generate_learning_path(
        self, project: ResearchProject, artifacts: list[Artifact], project_dir: Path,
    ) -> str | None:
        """Generate learning path from research frame and industry map."""
        # Find research frame artifact
        rf = next((a for a in artifacts if a.id == "ART-RESEARCH-FRAME"), None)
        if not rf:
            return None

        lines = [
            "---",
            f'project: "{project.title}"',
            'type: "learning_path"',
            "---\n",
            f"# {project.domain} 学习路径\n",
            "基于研究框架和行业地图生成的入局路径。\n",
            rf.content,
        ]

        path = project_dir / "学习路径.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return "学习路径.md"

    @staticmethod
    def _render_artifact(project: ResearchProject, artifact: Artifact) -> str:
        evidence_ids = ", ".join(artifact.source_evidence_ids)
        tags = f"[{artifact.artifact_type.value}]" if artifact.artifact_type else "[]"
        return (
            "---\n"
            f'project: "{project.title}"\n'
            f'artifact_type: "{artifact.artifact_type.value}"\n'
            f'schema_version: "{artifact.schema_version}"\n'
            f"evidence_ids: [{evidence_ids}]\n"
            f"tags: {tags}\n"
            f"generated_at: \"{datetime.now(UTC).strftime('%Y-%m-%d')}\"\n"
            "---\n\n"
            f"{artifact.content}\n"
        )

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9一-鿿]+", "-", value.lower()).strip("-")
        return slug or "sectorbreaker-project"
