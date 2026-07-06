"""Markdown and Obsidian-compatible export writer.

Exports are organized by the 5 steps from the design doc:
01-建立行业数据库, 02-反向拆解, 03-内容生态, 04-知识地图, 05-学习路径
"""

import json
import re
import shutil
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
    export_dir: str | None = None


class MarkdownExporter:
    def __init__(self, export_root: Path) -> None:
        self.export_root = export_root
        self.default_obsidian_config_dir = Path(__file__).resolve().parents[3] / ".obsidian"

    def export_project(
        self,
        project: ResearchProject,
        artifacts: list[Artifact],
        evidence: list[EvidenceItem],
    ) -> ExportManifest:
        project_dir = self.export_root / self._slugify(project.title)
        project_dir.mkdir(parents=True, exist_ok=True)
        self._copy_default_obsidian_config(project_dir)

        artifact_paths: list[str] = []

        # Write each artifact to its content_path
        for artifact in artifacts:
            relative_path = Path(artifact.content_path)
            output_path = project_dir / relative_path
            if output_path.exists() and output_path.is_dir():
                output_path = output_path / "index.md"
                relative_path = Path(relative_path) / "index.md"
            parent_path = output_path.parent
            if parent_path.exists() and parent_path.is_file():
                parent_path.unlink()
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
            export_dir=str(project_dir.resolve()),
        )
        (project_dir / "manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if "manifest.json" not in manifest.artifact_paths:
            manifest.artifact_paths.append("manifest.json")
            (project_dir / "manifest.json").write_text(
                json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return manifest

    def _copy_default_obsidian_config(self, project_dir: Path) -> None:
        """Copy the repository's preferred Obsidian vault settings into exports."""
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
        self, project: ResearchProject, artifacts: list[Artifact],
        evidence: list[EvidenceItem], project_dir: Path,
    ) -> str | None:
        """Generate project README with navigation."""
        if self._is_talent_vault(artifacts):
            return self._generate_talent_vault_readme(project, artifacts, evidence, project_dir)
        if self._is_v1_vault(artifacts):
            return self._generate_v1_vault_readme(project, artifacts, evidence, project_dir)

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

    def _generate_talent_vault_readme(
        self,
        project: ResearchProject,
        artifacts: list[Artifact],
        evidence: list[EvidenceItem],
        project_dir: Path,
    ) -> str:
        generated_date = datetime.now(UTC).strftime("%Y-%m-%d")
        artifacts_by_path = {artifact.content_path: artifact for artifact in artifacts}
        main_order = [
            ("00-岗位需求总览.md", "岗位需求总览"),
            ("01-岗位画像与分层.md", "岗位画像与分层"),
            ("02-技能需求矩阵.md", "技能需求矩阵"),
            ("03-公司与行业分布.md", "公司与行业分布"),
            ("04-薪资与经验要求.md", "薪资与经验要求"),
            ("05-学习路径与能力模型.md", "学习路径与能力模型"),
            ("06-作品集与项目要求.md", "作品集与项目要求"),
            ("99-待验证问题.md", "待验证问题"),
        ]
        skill_cards = self._artifacts_under(artifacts, "skills/")
        role_cards = self._artifacts_under(artifacts, "roles/")
        company_cards = self._artifacts_under(artifacts, "companies/")
        lines = [
            "---",
            f'project: "{project.title}"',
            'type: "talent_vault_home"',
            'project_mode: "talent_demand"',
            'status: "draft"',
            f"generated_at: \"{generated_date}\"",
            'tags: ["sectorbreaker", "talent-demand", "vault-home"]',
            "---\n",
            f"# {project.title} 人才需求情报库\n",
            f"**目标岗位**：{project.domain}  ",
            f"**市场范围**：{project.market_scope.value}  ",
            f"**研究深度**：{project.depth.value}\n",
            "## 怎么使用这个 Vault\n",
            "1. 先读 `[[00-岗位需求总览]]`，确认本轮样本量、信源结构和限制。",
            "2. 再读 `[[02-技能需求矩阵]]`，把高频技能拆成课程、招聘筛选项或能力模型。",
            "3. 最后看 `[[99-待验证问题]]`，决定下一轮要补哪些 JD、报告或企业来源。\n",
            "## 主文档入口\n",
        ]
        for path, label in main_order:
            if path in artifacts_by_path:
                lines.append(f"- [[{Path(path).stem}]] — {label}")
        lines.extend([
            "",
            "## 卡片入口\n",
            f"- 技能卡片：{len(skill_cards)} 张",
            *self._readme_card_links(skill_cards),
            f"- 岗位层级卡片：{len(role_cards)} 张",
            *self._readme_card_links(role_cards),
            f"- 公司卡片：{len(company_cards)} 张",
            *self._readme_card_links(company_cards),
            "",
            "## 证据与限制\n",
            "- [[evidence-ledger]] — 本轮证据账本",
            "- Source Coverage Matrix 已写入 `[[00-岗位需求总览]]`，用于判断样本是否足够。",
            "- 搜索摘要、外部 AI 报告和用户上传材料的可信度不同，关键结论应继续补证。",
            "",
            "## 导出信息\n",
            f"- 证据数量：{len(evidence)}",
            f"- 主文档数量：{sum(1 for path, _ in main_order if path in artifacts_by_path)}",
            f"- 卡片数量：{len(skill_cards) + len(role_cards) + len(company_cards)}",
            "- Manifest：[[manifest]]",
        ])
        readme_path = project_dir / "README.md"
        readme_path.write_text("\n".join(lines), encoding="utf-8")
        return "README.md"

    def _generate_v1_vault_readme(
        self,
        project: ResearchProject,
        artifacts: list[Artifact],
        evidence: list[EvidenceItem],
        project_dir: Path,
    ) -> str:
        generated_date = datetime.now(UTC).strftime("%Y-%m-%d")
        artifacts_by_path = {artifact.content_path: artifact for artifact in artifacts}
        main_order = [
            ("00-领域总览.md", "领域总览"),
            ("01-入门路线.md", "入门路线"),
            ("02-核心概念.md", "核心概念"),
            ("03-玩家与工具地图.md", "主流架构与工具地图"),
            ("04-趋势与证据.md", "趋势与证据"),
            ("05-问题与机会.md", "问题与机会"),
            ("99-待验证问题.md", "待验证问题"),
        ]
        concept_cards = self._artifacts_under(artifacts, "concepts/")
        architecture_cards = self._artifacts_under(artifacts, "architectures/")
        tool_cards = self._artifacts_under(artifacts, "tools/")
        question_cards = self._artifacts_under(artifacts, "questions/")
        lines = [
            "---",
            f'project: "{project.title}"',
            'type: "vault_home"',
            'status: "draft"',
            f"generated_at: \"{generated_date}\"",
            'tags: ["sectorbreaker", "vault-home"]',
            "---\n",
            f"# {project.title} 知识库首页\n",
            f"**领域**：{project.domain}  ",
            f"**市场范围**：{project.market_scope.value}  ",
            f"**研究深度**：{project.depth.value}\n",
            "## 怎么使用这个 Vault\n",
            "1. 先读主文档入口，建立领域边界、学习路线和当前趋势。",
            "2. 再进入知识卡片，沿着 `[[双向链接]]` 补概念、架构、工具和待验证问题。",
            "3. 最后回到 `_sources/evidence-ledger.md` 检查来源，把薄弱判断继续补证。\n",
            "## 主文档入口\n",
        ]
        for path, label in main_order:
            if path in artifacts_by_path:
                lines.append(f"- [[{Path(path).stem}]] — {label}")
        lines.extend([
            "",
            "## 知识卡片入口\n",
            f"- 概念卡片：{len(concept_cards)} 张",
            *self._readme_card_links(concept_cards),
            f"- 架构卡片：{len(architecture_cards)} 张",
            *self._readme_card_links(architecture_cards),
            f"- 工具卡片：{len(tool_cards)} 张",
            *self._readme_card_links(tool_cards),
            f"- 待验证问题：{len(question_cards)} 张",
            *self._readme_card_links(question_cards),
            "",
            "## 证据与待验证\n",
            "- [[evidence-ledger]] — 本轮证据账本",
            "- [[99-待验证问题]] — 下一轮补库问题清单",
            "",
            "## 如何继续补库\n",
            "- 新增来源后，先把链接、摘要和判断写回 `_sources/evidence-ledger.md`。",
            "- 如果出现新概念、新架构或新工具，优先补充对应卡片，再回链到主文档。",
            "- 对证据不足的判断保留“待验证”标记，不要把线索当作结论。",
            "",
            "## 导出信息\n",
            f"- 证据数量：{len(evidence)}",
            f"- 主文档数量：{sum(1 for path, _ in main_order if path in artifacts_by_path)}",
            f"- 知识卡片数量：{len(concept_cards) + len(architecture_cards) + len(tool_cards) + len(question_cards)}",
            "- Manifest：[[manifest]]",
        ])
        readme_path = project_dir / "README.md"
        readme_path.write_text("\n".join(lines), encoding="utf-8")
        return "README.md"

    @staticmethod
    def _is_v1_vault(artifacts: list[Artifact]) -> bool:
        paths = {artifact.content_path for artifact in artifacts}
        return "00-领域总览.md" in paths or any(artifact.schema_version.endswith("card") for artifact in artifacts)

    @staticmethod
    def _is_talent_vault(artifacts: list[Artifact]) -> bool:
        paths = {artifact.content_path for artifact in artifacts}
        return "00-岗位需求总览.md" in paths or any(artifact.schema_version.startswith("talent-v1") for artifact in artifacts)

    @staticmethod
    def _artifacts_under(artifacts: list[Artifact], prefix: str) -> list[Artifact]:
        return sorted(
            [artifact for artifact in artifacts if artifact.content_path.startswith(prefix)],
            key=lambda artifact: artifact.title,
        )

    @staticmethod
    def _readme_card_links(artifacts: list[Artifact], limit: int = 12) -> list[str]:
        if not artifacts:
            return ["  - 暂无"]
        lines = [f"  - [[{Path(artifact.content_path).stem}]]" for artifact in artifacts[:limit]]
        if len(artifacts) > limit:
            lines.append(f"  - 其余 {len(artifacts) - limit} 张卡片可在对应文件夹中继续查看")
        return lines

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

        evidence_path = project_dir / "_sources" / "evidence-ledger.md"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("\n".join(lines), encoding="utf-8")
        return "_sources/evidence-ledger.md"

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
        evidence_ids = ", ".join(f'"{item}"' for item in artifact.source_evidence_ids)
        tags = f'["sectorbreaker", "{artifact.artifact_type.value}"]' if artifact.artifact_type else '["sectorbreaker"]'
        alias = artifact.title.replace('"', '\\"')
        artifact_kind = "knowledge_card" if artifact.schema_version.endswith("card") else "main_artifact"
        status = "needs_review" if not artifact.source_evidence_ids else "draft"
        return (
            "---\n"
            f'project: "{project.title}"\n'
            f'aliases: ["{alias}"]\n'
            f'type: "{artifact_kind}"\n'
            f'project_mode: "{getattr(project, "project_mode", "domain_knowledge").value}"\n'
            f'status: "{status}"\n'
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
