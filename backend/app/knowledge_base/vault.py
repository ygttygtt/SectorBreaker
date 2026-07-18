"""Safe Markdown vault import and deterministic health auditing."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from backend.app.schemas import (
    Artifact,
    ArtifactType,
    FindingSeverity,
    HealthFinding,
    HealthFindingType,
    KnowledgeHealthReport,
    MaintenanceTask,
    ResearchProject,
    VaultImportRecord,
    VaultImportRequest,
    VaultNoteSummary,
    VaultStatus,
)
from backend.app.storage.sqlite import SQLiteRepository


_IGNORED_PARTS = {".git", ".obsidian", ".sectorbreaker", ".trash", "node_modules", "__pycache__"}
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_EVIDENCE_RE = re.compile(r"\bEV-[A-Za-z0-9_-]+\b")
_UNRESOLVED_RE = re.compile(r"\b(?:TODO|FIXME)\b|待补证|待验证|未解决", re.IGNORECASE)


class VaultKnowledgeService:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def import_vault(self, project: ResearchProject, request: VaultImportRequest) -> VaultImportRecord:
        root = Path(request.source_path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("vault source path must be an existing directory")

        scanned: list[tuple[str, str, int, str]] = []
        skipped: list[str] = []
        total_bytes = 0
        candidates = sorted(
            root.rglob("*.md"),
            key=lambda candidate: _vault_path_sort_key(candidate.relative_to(root)),
        )
        for candidate in candidates:
            relative = candidate.relative_to(root)
            relative_posix = relative.as_posix()
            if any(part in _IGNORED_PARTS or part.startswith(".") for part in relative.parts):
                skipped.append(relative_posix)
                continue
            resolved = candidate.resolve()
            if root != resolved and root not in resolved.parents:
                raise ValueError(f"vault note escapes source root: {relative_posix}")
            if not candidate.is_file():
                skipped.append(relative_posix)
                continue
            raw = candidate.read_bytes()
            total_bytes += len(raw)
            if len(scanned) + 1 > request.max_files:
                raise ValueError(f"vault exceeds max_files={request.max_files}")
            if total_bytes > request.max_total_bytes:
                raise ValueError(f"vault exceeds max_total_bytes={request.max_total_bytes}")
            try:
                content = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError(f"vault note is not UTF-8: {relative_posix}") from exc
            content_hash = _content_hash(content)
            scanned.append((relative_posix, content, len(raw), content_hash))

        snapshot = sha256()
        for relative_path, _, size, content_hash in scanned:
            snapshot.update(relative_path.encode("utf-8"))
            snapshot.update(str(size).encode("ascii"))
            snapshot.update(content_hash.encode("ascii"))
        snapshot_hash = "sha256:" + snapshot.hexdigest()

        latest = self.repository.latest_vault_import(project.id)
        if latest is not None and latest.snapshot_hash == snapshot_hash:
            return latest

        active_by_path = {artifact.content_path: artifact for artifact in self.repository.list_artifacts(project.id)}
        imported_paths: list[str] = []
        for relative_path, content, _, content_hash in scanned:
            current = active_by_path.get(relative_path)
            if current is not None and current.content_hash == content_hash:
                imported_paths.append(relative_path)
                continue
            artifact = Artifact(
                id=f"ART-VAULT-{uuid4().hex[:12]}",
                project_id=project.id,
                artifact_type=ArtifactType.VAULT_NOTE,
                title=_note_title(relative_path, content),
                content_path=relative_path,
                content=content,
                source_evidence_ids=sorted(set(_EVIDENCE_RE.findall(content))),
                schema_version="v3-knowledge-ops",
                supersedes=current.id if current is not None else None,
            )
            self.repository.add_artifact(artifact)
            imported_paths.append(relative_path)

        record = VaultImportRecord(
            id=f"VI-{uuid4().hex[:12]}",
            project_id=project.id,
            source_path=str(root),
            note_count=len(scanned),
            total_bytes=total_bytes,
            snapshot_hash=snapshot_hash,
            imported_paths=imported_paths,
            skipped_paths=skipped,
            created_at=datetime.now(UTC),
        )
        self.repository.save_vault_import(record)
        return record

    def status(self, project_id: str) -> VaultStatus:
        artifacts = [
            item for item in self.repository.list_artifacts(project_id)
            if item.artifact_type == ArtifactType.VAULT_NOTE
        ]
        notes = [
            VaultNoteSummary(
                artifact_id=item.id,
                relative_path=item.content_path,
                title=item.title,
                revision=item.revision,
                content_hash=item.content_hash,
                wikilinks=_wikilinks(item.content),
                tags=_frontmatter_list(item.content, "tags"),
            )
            for item in artifacts
        ]
        return VaultStatus(
            project_id=project_id,
            latest_import=self.repository.latest_vault_import(project_id),
            active_note_count=len(notes),
            notes=notes,
        )

    def audit(self, project_id: str) -> KnowledgeHealthReport:
        artifacts = [
            item for item in self.repository.list_artifacts(project_id)
            if item.content_path.lower().endswith(".md")
        ]
        latest_import = self.repository.latest_vault_import(project_id)
        snapshot_hash = _artifact_snapshot_hash(artifacts)
        findings: list[HealthFinding] = []

        titles: dict[str, list[Artifact]] = {}
        aliases: dict[str, str] = {}
        links_by_path: dict[str, list[str]] = {}
        for artifact in artifacts:
            normalized_title = _normalize_link(artifact.title)
            titles.setdefault(normalized_title, []).append(artifact)
            path_without_suffix = artifact.content_path.removesuffix(".md")
            for alias in {artifact.title, Path(path_without_suffix).name, path_without_suffix}:
                aliases[_normalize_link(alias)] = artifact.content_path
            links_by_path[artifact.content_path] = _wikilinks(artifact.content)

            if not artifact.content.lstrip().startswith("---\n"):
                findings.append(_finding(
                    project_id,
                    HealthFindingType.MISSING_FRONTMATTER,
                    [artifact.content_path],
                    "笔记缺少 YAML front matter，版本、标签和证据元数据无法稳定维护。",
                    "补充最小 front matter，并保留原正文。",
                    auto_fixable=True,
                ))
            if "evidence_ids:" not in artifact.content[:1600]:
                findings.append(_finding(
                    project_id,
                    HealthFindingType.MISSING_EVIDENCE_METADATA,
                    [artifact.content_path],
                    "笔记没有 evidence_ids 元数据；事实性内容无法追溯来源。",
                    "判断该笔记是否包含事实主张，并补充证据或明确标记为个人笔记。",
                ))
            if _UNRESOLVED_RE.search(artifact.content):
                findings.append(_finding(
                    project_id,
                    HealthFindingType.UNRESOLVED_MARKER,
                    [artifact.content_path],
                    "笔记包含 TODO、待补证或待验证标记。",
                    "将未解决标记转成维护任务，补充材料后再修订。",
                ))

        for duplicate_group in titles.values():
            if len(duplicate_group) > 1:
                paths = sorted(item.content_path for item in duplicate_group)
                findings.append(_finding(
                    project_id,
                    HealthFindingType.DUPLICATE_TITLE,
                    paths,
                    "多篇笔记使用相同标题，wikilink 解析和检索可能产生歧义。",
                    "确认它们是不同概念还是重复内容，再决定重命名或合并。",
                ))

        inbound = {artifact.content_path: 0 for artifact in artifacts}
        for source_path, links in links_by_path.items():
            for link in links:
                target_path = aliases.get(_normalize_link(link))
                if target_path is None:
                    findings.append(_finding(
                        project_id,
                        HealthFindingType.BROKEN_LINK,
                        [source_path],
                        f"wikilink [[{link}]] 没有对应的活跃笔记。",
                        "修正链接目标，或创建缺失的概念卡片。",
                        auto_fixable=False,
                    ))
                else:
                    inbound[target_path] = inbound.get(target_path, 0) + 1

        if len(artifacts) > 1:
            for artifact in artifacts:
                stem = Path(artifact.content_path).stem.lower()
                if stem in {"readme", "index", "home", "首页"}:
                    continue
                if inbound.get(artifact.content_path, 0) == 0 and not links_by_path.get(artifact.content_path):
                    findings.append(_finding(
                        project_id,
                        HealthFindingType.ORPHAN_NOTE,
                        [artifact.content_path],
                        "笔记既没有入链也没有出链，当前处于知识图谱孤岛。",
                        "判断其归属，并链接到索引、主文档或相关概念。",
                        auto_fixable=False,
                    ))

        metrics = {
            "active_notes": len(artifacts),
            "findings": len(findings),
            "broken_links": sum(item.finding_type == HealthFindingType.BROKEN_LINK for item in findings),
            "orphan_notes": sum(item.finding_type == HealthFindingType.ORPHAN_NOTE for item in findings),
            "duplicate_titles": sum(item.finding_type == HealthFindingType.DUPLICATE_TITLE for item in findings),
            "missing_frontmatter": sum(item.finding_type == HealthFindingType.MISSING_FRONTMATTER for item in findings),
            "missing_evidence_metadata": sum(
                item.finding_type == HealthFindingType.MISSING_EVIDENCE_METADATA for item in findings
            ),
        }
        report = KnowledgeHealthReport(
            id=f"KHR-{uuid4().hex[:12]}",
            project_id=project_id,
            vault_import_id=latest_import.id if latest_import else None,
            snapshot_hash=snapshot_hash,
            metrics=metrics,
            findings=findings,
        )
        self.repository.save_health_report(report)
        for finding in findings:
            task = _task_for_finding(project_id, finding)
            self.repository.upsert_maintenance_task(task)
        return report


def _finding(
    project_id: str,
    finding_type: HealthFindingType,
    target_paths: list[str],
    explanation: str,
    suggested_action: str,
    *,
    auto_fixable: bool = False,
) -> HealthFinding:
    fingerprint = "|".join([project_id, finding_type.value, *sorted(target_paths), explanation])
    finding_id = "HF-" + sha256(fingerprint.encode("utf-8")).hexdigest()[:12]
    return HealthFinding(
        id=finding_id,
        finding_type=finding_type,
        severity=FindingSeverity.WARNING,
        target_paths=target_paths,
        explanation=explanation,
        suggested_action=suggested_action,
        auto_fixable=auto_fixable,
    )


def _task_for_finding(project_id: str, finding: HealthFinding) -> MaintenanceTask:
    fingerprint_text = "|".join([project_id, finding.finding_type.value, *sorted(finding.target_paths)])
    fingerprint = sha256(fingerprint_text.encode("utf-8")).hexdigest()
    return MaintenanceTask(
        id="MT-" + fingerprint[:12],
        project_id=project_id,
        fingerprint=fingerprint,
        finding_ids=[finding.id],
        task_type=finding.finding_type.value,
        objective=finding.suggested_action,
        target_paths=finding.target_paths,
        priority=2 if finding.auto_fixable else 3,
        assigned_specialist="vault_auditor" if not finding.auto_fixable else "knowledge_editor",
        approval_required=True,
    )


def _note_title(relative_path: str, content: str) -> str:
    title = _frontmatter_scalar(content, "title")
    if title:
        return title
    heading = _H1_RE.search(content)
    return heading.group(1).strip() if heading else Path(relative_path).stem


def _wikilinks(content: str) -> list[str]:
    links: list[str] = []
    for raw in _WIKILINK_RE.findall(content):
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            links.append(target)
    return list(dict.fromkeys(links))


def _frontmatter_scalar(content: str, key: str) -> str:
    if not content.lstrip().startswith("---\n"):
        return ""
    end = content.find("\n---", 4)
    if end < 0:
        return ""
    match = re.search(rf"(?m)^{re.escape(key)}:\s*[\"']?(.+?)[\"']?\s*$", content[4:end])
    return match.group(1).strip() if match else ""


def _frontmatter_list(content: str, key: str) -> list[str]:
    value = _frontmatter_scalar(content, key)
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [item.strip().strip("\"'") for item in value.split(",") if item.strip()]


def _normalize_link(value: str) -> str:
    return value.replace("\\", "/").removesuffix(".md").strip(" /").casefold()


def _vault_path_sort_key(relative_path: Path) -> tuple[int, str]:
    """Keep import ordering deterministic across case-sensitive and Windows filesystems."""
    return len(relative_path.parts), relative_path.as_posix().casefold()


def _content_hash(content: str) -> str:
    return "sha256:" + sha256(content.encode("utf-8")).hexdigest()


def _artifact_snapshot_hash(artifacts: list[Artifact]) -> str:
    digest = sha256()
    for artifact in sorted(artifacts, key=lambda item: item.content_path):
        digest.update(artifact.content_path.encode("utf-8"))
        digest.update(artifact.content_hash.encode("ascii"))
    return "sha256:" + digest.hexdigest()
