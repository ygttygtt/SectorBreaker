"""V3 Markdown and Obsidian-compatible knowledge-base export."""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field

from backend.app.agent_state import ArtifactMemory, SectorBreakerState
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ChangeSet,
    EvidenceItem,
    KnowledgeHealthReport,
    MaintenanceTask,
    ResearchProject,
    RunEvent,
)


V3_SCHEMA_VERSION = "v3-knowledge-ops"
V3_EXPORT_VERSION = "3"
_CARD_FOLDERS = {"architectures", "concepts", "notes", "players", "processes", "questions", "risks", "tools"}
_MANAGED_FRONTMATTER_KEYS = {
    "project",
    "artifact_id",
    "artifact_type",
    "schema_version",
    "revision",
    "content_hash",
    "status",
    "evidence_ids",
    "tags",
    "generated_at",
}


class ExportManifest(BaseModel):
    export_version: str = V3_EXPORT_VERSION
    schema_version: str = V3_SCHEMA_VERSION
    project_id: str
    generated_at: datetime
    artifact_paths: list[str]
    evidence_ids: list[str]
    export_dir: str | None = None
    active_artifacts: list[dict[str, object]] = Field(default_factory=list)
    latest_health_snapshot_id: str | None = None
    maintenance_task_summary: dict[str, int] = Field(default_factory=dict)
    change_set_summary: dict[str, int] = Field(default_factory=dict)
    app_version: str | None = None


class MarkdownExporter:
    def __init__(self, export_root: Path) -> None:
        self.export_root = export_root
        self.default_obsidian_config_dir = Path(__file__).resolve().parents[3] / ".obsidian"

    def export_project(
        self,
        project: ResearchProject,
        artifacts: list[Artifact],
        evidence: list[EvidenceItem],
        run_events: list[RunEvent] | None = None,
        *,
        agent_state: SectorBreakerState | None = None,
        health_snapshot: KnowledgeHealthReport | None = None,
        maintenance_backlog: list[MaintenanceTask] | None = None,
        change_sets: list[ChangeSet] | None = None,
        app_version: str | None = None,
    ) -> ExportManifest:
        """Export one inspectable V3 vault containing active revisions only."""
        active_artifacts = self._active_artifacts(artifacts)
        backlog = maintenance_backlog or []
        changes = change_sets or []
        events = run_events or []

        project_dir = self.export_root / self._slugify(project.title)
        project_dir.mkdir(parents=True, exist_ok=True)
        self._clean_previous_managed_export(project_dir)
        self._copy_default_obsidian_config(project_dir)

        artifact_paths: list[str] = []
        export_paths_by_id: dict[str, str] = {}
        occupied_paths: dict[str, str] = {}
        for artifact in active_artifacts:
            relative_path = self._resolve_artifact_export_path(artifact)
            collision_key = relative_path.casefold()
            if collision_key in occupied_paths:
                raise ValueError(
                    "multiple active artifacts resolve to the same export path: "
                    f"{occupied_paths[collision_key]} and {artifact.id} -> {relative_path}"
                )
            occupied_paths[collision_key] = artifact.id
            output_path = project_dir / Path(relative_path)
            if output_path.exists() and output_path.is_dir():
                raise ValueError(f"artifact export path is a directory: {relative_path}")
            if output_path.parent.exists() and output_path.parent.is_file():
                raise ValueError(f"artifact export parent is a file: {relative_path}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(self._render_artifact(project, artifact), encoding="utf-8")
            artifact_paths.append(relative_path)
            export_paths_by_id[artifact.id] = relative_path

        evidence_path = self._generate_evidence_index(project, evidence, project_dir)
        if evidence_path:
            artifact_paths.append(evidence_path)

        readme_path = self._generate_readme(
            project,
            active_artifacts,
            evidence,
            project_dir,
            export_paths_by_id,
        )
        artifact_paths.append(readme_path)

        state_paths = self._generate_sectorbreaker_state_bundle(
            project=project,
            artifacts=active_artifacts,
            evidence=evidence,
            run_events=events,
            project_dir=project_dir,
            export_paths_by_id=export_paths_by_id,
            agent_state=agent_state,
            health_snapshot=health_snapshot,
            maintenance_backlog=backlog,
            change_sets=changes,
        )
        artifact_paths.extend(state_paths)

        generated_at = datetime.now(UTC)
        manifest = ExportManifest(
            project_id=project.id,
            generated_at=generated_at,
            artifact_paths=[*artifact_paths, "manifest.json"],
            evidence_ids=[item.id for item in evidence],
            export_dir=str(project_dir.resolve()),
            active_artifacts=[
                {
                    "id": artifact.id,
                    "path": export_paths_by_id[artifact.id],
                    "source_content_path": artifact.content_path,
                    "revision": artifact.revision,
                    "content_hash": artifact.content_hash,
                    "artifact_type": artifact.artifact_type.value,
                    "evidence_ids": artifact.source_evidence_ids,
                }
                for artifact in active_artifacts
            ],
            latest_health_snapshot_id=health_snapshot.id if health_snapshot else None,
            maintenance_task_summary=dict(Counter(task.status.value for task in backlog)),
            change_set_summary=dict(Counter(item.status.value for item in changes)),
            app_version=app_version,
        )
        (project_dir / "manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    @staticmethod
    def _clean_previous_managed_export(project_dir: Path) -> None:
        """Remove files recorded by the prior manifest so inactive revisions cannot linger."""
        manifest_path = project_dir / "manifest.json"
        if not manifest_path.is_file():
            return
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return
        recorded_paths = previous.get("artifact_paths", [])
        if not isinstance(recorded_paths, list):
            return
        project_root = project_dir.resolve()
        for raw_path in recorded_paths:
            if not isinstance(raw_path, str):
                continue
            candidate = (project_dir / raw_path).resolve()
            if project_root not in candidate.parents or not candidate.is_file():
                continue
            candidate.unlink()
        for directory in sorted(
            (item for item in project_dir.rglob("*") if item.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            if directory.name == ".obsidian":
                continue
            try:
                directory.rmdir()
            except OSError:
                pass

    def _generate_sectorbreaker_state_bundle(
        self,
        *,
        project: ResearchProject,
        artifacts: list[Artifact],
        evidence: list[EvidenceItem],
        run_events: list[RunEvent],
        project_dir: Path,
        export_paths_by_id: dict[str, str],
        agent_state: SectorBreakerState | None,
        health_snapshot: KnowledgeHealthReport | None,
        maintenance_backlog: list[MaintenanceTask],
        change_sets: list[ChangeSet],
    ) -> list[str]:
        state_dir = project_dir / ".sectorbreaker"
        state_dir.mkdir(parents=True, exist_ok=True)

        export_state = self._complete_agent_state(
            project=project,
            artifacts=artifacts,
            state=agent_state,
            health_snapshot=health_snapshot,
            maintenance_backlog=maintenance_backlog,
        )
        open_questions = [item.model_dump(mode="json") for item in export_state.shared_knowledge.open_questions]
        question_artifacts = [
            {
                "artifact_id": artifact.id,
                "title": artifact.title,
                "content_path": export_paths_by_id[artifact.id],
                "revision": artifact.revision,
                "content_hash": artifact.content_hash,
                "evidence_ids": artifact.source_evidence_ids,
            }
            for artifact in artifacts
            if artifact.artifact_type == ArtifactType.UNRESOLVED_QUESTIONS
            or artifact.content_path.startswith("questions/")
        ]
        trace_summary = [self._serialize_event(event) for event in run_events[-120:]]

        files: dict[str, object] = {
            "project.json": project.model_dump(mode="json"),
            "agent_state.json": export_state.model_dump(mode="json"),
            "evidence_ledger.json": [item.model_dump(mode="json") for item in evidence],
            "artifact_manifest.json": [
                {
                    "id": artifact.id,
                    "artifact_type": artifact.artifact_type.value,
                    "title": artifact.title,
                    "content_path": export_paths_by_id[artifact.id],
                    "source_content_path": artifact.content_path,
                    "schema_version": V3_SCHEMA_VERSION,
                    "revision": artifact.revision,
                    "content_hash": artifact.content_hash,
                    "status": "active",
                    "supersedes": artifact.supersedes,
                    "superseded_by": artifact.superseded_by,
                    "run_id": artifact.run_id,
                    "change_set_id": artifact.change_set_id,
                    "source_evidence_ids": artifact.source_evidence_ids,
                    "created_at": artifact.created_at.isoformat(),
                }
                for artifact in artifacts
            ],
            "health_snapshot.json": (
                health_snapshot.model_dump(mode="json")
                if health_snapshot
                else {"project_id": project.id, "status": "not_generated", "report": None}
            ),
            "maintenance_backlog.json": [item.model_dump(mode="json") for item in maintenance_backlog],
            "change_sets.json": [self._serialize_change_set(item) for item in change_sets],
            "open_questions.json": {
                "state_questions": open_questions,
                "question_artifacts": question_artifacts,
            },
            "trace_summary.json": trace_summary,
        }

        written: list[str] = []
        for filename, payload in files.items():
            path = state_dir / filename
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(f".sectorbreaker/{filename}")
        return written

    @staticmethod
    def _serialize_change_set(change_set: ChangeSet) -> dict[str, object]:
        payload = change_set.model_dump(mode="json")
        for operation in payload["operations"]:
            before_content = str(operation.get("before_content", ""))
            after_content = str(operation.get("after_content", ""))
            operation["before_hash"] = "sha256:" + sha256(before_content.encode("utf-8")).hexdigest()
            operation["after_hash"] = "sha256:" + sha256(after_content.encode("utf-8")).hexdigest()
        return payload

    @staticmethod
    def _complete_agent_state(
        *,
        project: ResearchProject,
        artifacts: list[Artifact],
        state: SectorBreakerState | None,
        health_snapshot: KnowledgeHealthReport | None,
        maintenance_backlog: list[MaintenanceTask],
    ) -> SectorBreakerState:
        export_state = state.model_copy(deep=True) if state is not None else SectorBreakerState.initialize(
            project_id=project.id,
            domain=project.domain,
            user_goal=f"维护 {project.title} 知识库",
            market_scope=project.market_scope.value,
            source_policy=project.source_policy.value,
        )
        export_state.state_version = "3"
        memories_by_id = {item.artifact_id: item for item in export_state.artifact_memory}
        for artifact in artifacts:
            memories_by_id[artifact.id] = ArtifactMemory(
                artifact_id=artifact.id,
                content_path=artifact.content_path,
                title=artifact.title,
                revision=artifact.revision,
                content_hash=artifact.content_hash,
                active=True,
                supersedes=artifact.supersedes,
                superseded_by=artifact.superseded_by,
                review_status="active",
                last_modified_run_id=artifact.run_id,
            )
        export_state.artifact_memory = list(memories_by_id.values())
        if health_snapshot is not None:
            export_state.latest_health_report_id = health_snapshot.id
            export_state.vault_import_id = health_snapshot.vault_import_id or export_state.vault_import_id
        export_state.maintenance_task_ids = [item.id for item in maintenance_backlog]
        export_state.maintenance_task_summaries = [
            f"{item.id} [{item.status.value}] {item.objective}" for item in maintenance_backlog
        ]
        return export_state

    @staticmethod
    def _serialize_event(event: RunEvent) -> dict[str, object]:
        timestamp = event.timestamp
        if hasattr(timestamp, "isoformat"):
            serialized_timestamp = timestamp.isoformat()
        else:
            serialized_timestamp = datetime.fromtimestamp(float(timestamp), tz=UTC).isoformat()
        return {
            "event_type": event.event_type,
            "gate": event.gate,
            "step": event.step,
            "agent": event.agent,
            "message": event.message,
            "severity": event.severity,
            "timestamp": serialized_timestamp,
            "data": event.data,
        }

    def _copy_default_obsidian_config(self, project_dir: Path) -> None:
        if not self.default_obsidian_config_dir.is_dir():
            return
        target_dir = project_dir / ".obsidian"
        for source_path in self.default_obsidian_config_dir.rglob("*"):
            relative_path = source_path.relative_to(self.default_obsidian_config_dir)
            target_path = target_dir / relative_path
            if source_path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)

    def _generate_readme(
        self,
        project: ResearchProject,
        artifacts: list[Artifact],
        evidence: list[EvidenceItem],
        project_dir: Path,
        export_paths_by_id: dict[str, str],
    ) -> str:
        readme_name = "SectorBreaker Home.md" if "readme.md" in {
            path.casefold() for path in export_paths_by_id.values()
        } else "README.md"
        groups: dict[str, list[Artifact]] = {"docs": [], "cards": [], "followups": [], "vault": []}
        for artifact in artifacts:
            path = export_paths_by_id[artifact.id]
            top = PurePosixPath(path).parts[0]
            groups[top if top in {"docs", "cards", "followups"} else "vault"].append(artifact)

        lines = [
            "---",
            f"project: {json.dumps(project.title, ensure_ascii=False)}",
            'type: "knowledge_base_home"',
            f'schema_version: "{V3_SCHEMA_VERSION}"',
            'status: "active"',
            f'generated_at: "{datetime.now(UTC).isoformat()}"',
            'tags: ["sectorbreaker", "knowledge-ops", "vault-home"]',
            "---\n",
            f"# {project.title}\n",
            f"**领域**：{project.domain}  ",
            f"**市场范围**：{project.market_scope.value}  ",
            f"**研究深度**：{project.depth.value}\n",
            "## 知识库入口\n",
        ]
        labels = {
            "docs": "主文档",
            "cards": "知识卡片",
            "followups": "追问与增量笔记",
            "vault": "导入 Vault 笔记",
        }
        for group_name in ("docs", "cards", "followups", "vault"):
            group = sorted(groups[group_name], key=lambda item: export_paths_by_id[item.id])
            if not group:
                continue
            lines.append(f"### {labels[group_name]}：{len(group)} 篇\n")
            for artifact in group:
                path = export_paths_by_id[artifact.id].removesuffix(".md")
                lines.append(f"- [[{path}|{artifact.title}]] · revision {artifact.revision}")
            lines.append("")
        lines.extend([
            "## 证据与自治维护\n",
            "- [[sources/evidence-ledger|证据账本]]",
            "- `.sectorbreaker/health_snapshot.json`：最近一次确定性健康审计",
            "- `.sectorbreaker/maintenance_backlog.json`：持续维护任务",
            "- `.sectorbreaker/change_sets.json`：审批、应用与回滚历史",
            "- `.sectorbreaker/agent_state.json`：完整可检查 Agent State",
            "",
            "## 导出摘要\n",
            f"- 活跃知识 revision：{len(artifacts)}",
            f"- 证据条目：{len(evidence)}",
            "- 仅 active revisions 进入本 Vault；历史 revision 保留在 SQLite 与 ChangeSet 记录中。",
        ])
        path = project_dir / readme_name
        path.write_text("\n".join(lines), encoding="utf-8")
        return readme_name

    @staticmethod
    def _generate_evidence_index(
        project: ResearchProject,
        evidence: list[EvidenceItem],
        project_dir: Path,
    ) -> str | None:
        if not evidence:
            return None
        lines = [
            "---",
            f"project: {json.dumps(project.title, ensure_ascii=False)}",
            'type: "evidence_index"',
            f'schema_version: "{V3_SCHEMA_VERSION}"',
            'status: "active"',
            "---\n",
            f"# {project.title} 证据账本\n",
        ]
        for item in evidence:
            source = item.source_title or item.id
            url = f" — [链接]({item.source_url})" if item.source_url else ""
            confidence = f" · 可信度 {item.confidence}" if item.confidence is not None else ""
            lines.extend([
                f"### {item.id}",
                f"**来源**：{source}{url}{confidence}",
                f"**验证状态**：{item.verification_status.value}",
                f"> {(item.snippet or item.summary or item.raw_excerpt)[:400]}",
                "",
            ])
        path = project_dir / "sources" / "evidence-ledger.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return "sources/evidence-ledger.md"

    @staticmethod
    def _active_artifacts(artifacts: list[Artifact]) -> list[Artifact]:
        return sorted(
            [artifact for artifact in artifacts if artifact.active],
            key=lambda artifact: (artifact.content_path.casefold(), artifact.revision, artifact.id),
        )

    @staticmethod
    def _resolve_artifact_export_path(artifact: Artifact) -> str:
        relative_path = MarkdownExporter._safe_relative_markdown_path(
            artifact.content_path or f"{artifact.id}.md"
        )
        path = PurePosixPath(relative_path)
        if artifact.artifact_type == ArtifactType.VAULT_NOTE:
            return path.as_posix()
        if artifact.artifact_type == ArtifactType.FOLLOW_UP_NOTE:
            return path.as_posix() if path.parts[0] == "followups" else (PurePosixPath("followups") / path.name).as_posix()
        if path.parts[0] in {"docs", "cards", "followups"}:
            return path.as_posix()
        if path.parts[0] in _CARD_FOLDERS or artifact.schema_version.endswith("card"):
            return (PurePosixPath("cards") / path).as_posix()
        return (PurePosixPath("docs") / path.name).as_posix()

    @staticmethod
    def _safe_relative_markdown_path(value: str) -> str:
        normalized = value.replace("\\", "/").strip("/")
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"artifact path must be a safe relative path: {value}")
        if path.parts[0].startswith(".") or path.as_posix().casefold() in {
            "manifest.json",
            "sources/evidence-ledger.md",
        }:
            raise ValueError(f"artifact path collides with export control files: {value}")
        if path.suffix.casefold() != ".md":
            raise ValueError(f"artifact export supports Markdown only: {value}")
        return path.as_posix()

    @staticmethod
    def _render_artifact(project: ResearchProject, artifact: Artifact) -> str:
        frontmatter, body = MarkdownExporter._split_leading_frontmatter(artifact.content)
        original_tags = MarkdownExporter._frontmatter_list(frontmatter, "tags")
        original_evidence_ids = MarkdownExporter._frontmatter_list(frontmatter, "evidence_ids")
        preserved = MarkdownExporter._preserved_frontmatter(frontmatter)
        evidence_ids = list(dict.fromkeys([*artifact.source_evidence_ids, *original_evidence_ids]))
        tags = list(dict.fromkeys(["sectorbreaker", artifact.artifact_type.value, *original_tags]))
        lines = [
            "---",
            f"project: {json.dumps(project.title, ensure_ascii=False)}",
            f"artifact_id: {json.dumps(artifact.id, ensure_ascii=False)}",
            f"artifact_type: {json.dumps(artifact.artifact_type.value, ensure_ascii=False)}",
            f'schema_version: "{V3_SCHEMA_VERSION}"',
            f"revision: {artifact.revision}",
            f"content_hash: {json.dumps(artifact.content_hash, ensure_ascii=False)}",
            'status: "active"',
            f"evidence_ids: {json.dumps(evidence_ids, ensure_ascii=False)}",
            f"tags: {json.dumps(tags, ensure_ascii=False)}",
            f'generated_at: "{artifact.created_at.isoformat()}"',
        ]
        if preserved:
            lines.extend(preserved)
        lines.extend(["---", "", body.rstrip(), ""])
        return "\n".join(lines)

    @staticmethod
    def _split_leading_frontmatter(content: str) -> tuple[list[str], str]:
        stripped = content.lstrip("\ufeff \t\r\n")
        if not stripped.startswith("---\n"):
            return [], content
        match = re.search(r"(?m)^---\s*$", stripped[4:])
        if match is None:
            return [], content
        end = 4 + match.start()
        body_start = 4 + match.end()
        return stripped[4:end].splitlines(), stripped[body_start:].lstrip("\r\n")

    @staticmethod
    def _frontmatter_list(lines: list[str], key: str) -> list[str]:
        for index, line in enumerate(lines):
            match = re.match(rf"^{re.escape(key)}:\s*(.*)$", line, flags=re.IGNORECASE)
            if match is None:
                continue
            value = match.group(1).strip()
            if value.startswith("[") and value.endswith("]"):
                try:
                    parsed = json.loads(value.replace("'", '"'))
                except (json.JSONDecodeError, TypeError):
                    parsed = [item.strip().strip("\"'") for item in value[1:-1].split(",")]
                return [str(item) for item in parsed if str(item).strip()]
            if value:
                return [value.strip("\"'")]
            items: list[str] = []
            for child in lines[index + 1:]:
                if child.startswith((" ", "\t")):
                    child_value = child.strip()
                    if child_value.startswith("-"):
                        items.append(child_value[1:].strip().strip("\"'"))
                    continue
                break
            return [item for item in items if item]
        return []

    @staticmethod
    def _preserved_frontmatter(lines: list[str]) -> list[str]:
        preserved: list[str] = []
        skip_block = False
        for line in lines:
            top_level = bool(line) and not line.startswith((" ", "\t"))
            if top_level:
                key = line.split(":", 1)[0].strip().casefold() if ":" in line else ""
                skip_block = key in _MANAGED_FRONTMATTER_KEYS
            if not skip_block:
                preserved.append(line)
        while preserved and not preserved[-1].strip():
            preserved.pop()
        return preserved

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9一-鿿]+", "-", value.lower()).strip("-")
        return slug or "sectorbreaker-project"
