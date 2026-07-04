from pathlib import Path

from backend.app.exporters.markdown import MarkdownExporter
from backend.app.schemas import EvidenceItem, MarketScope, ProjectMode, ResearchDepth, ResearchProject, VerificationStatus
from backend.app.talent_demand.export import build_talent_demand_artifacts
from backend.app.talent_demand.models import (
    JobPostingSignal,
    SkillDemandItem,
    SourceCoverageMatrix,
    TalentDemandKnowledgeBase,
)


def test_talent_demand_export_renders_main_docs_and_cards() -> None:
    project, knowledge_base = _project_and_knowledge_base()

    artifacts = build_talent_demand_artifacts(project=project, knowledge_base=knowledge_base)
    paths = {artifact.content_path for artifact in artifacts}

    assert "00-岗位需求总览.md" in paths
    assert "02-技能需求矩阵.md" in paths
    assert "skills/RAG.md" in paths
    overview = next(artifact for artifact in artifacts if artifact.content_path == "00-岗位需求总览.md")
    assert "Source Coverage Matrix" in overview.content
    assert "source_coverage" in overview.content


def test_markdown_exporter_writes_talent_demand_vault_readme(tmp_path: Path) -> None:
    project, knowledge_base = _project_and_knowledge_base()
    artifacts = build_talent_demand_artifacts(project=project, knowledge_base=knowledge_base)
    evidence = [
        EvidenceItem(
            id="EV-JD-1",
            project_id=project.id,
            source_title="JD sample",
            snippet="岗位：大模型应用开发工程师",
            confidence=0.7,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        )
    ]

    manifest = MarkdownExporter(tmp_path).export_project(project, artifacts, evidence)
    project_dir = tmp_path / "大模型应用开发工程师需求"

    assert "README.md" in manifest.artifact_paths
    readme = (project_dir / "README.md").read_text(encoding="utf-8")
    overview = (project_dir / "00-岗位需求总览.md").read_text(encoding="utf-8")
    assert "人才需求情报库" in readme
    assert "[[02-技能需求矩阵]]" in readme
    assert "project_mode: \"talent_demand\"" in overview


def _project_and_knowledge_base() -> tuple[ResearchProject, TalentDemandKnowledgeBase]:
    project = ResearchProject(
        id="project-talent",
        title="大模型应用开发工程师需求",
        domain="大模型应用开发工程师",
        market_scope=MarketScope.CHINA,
        depth=ResearchDepth.QUICK,
        project_mode=ProjectMode.TALENT_DEMAND,
    )
    knowledge_base = TalentDemandKnowledgeBase(
        overview="岗位需求集中在 RAG、Agent 和 Python 工程化。",
        postings=[
            JobPostingSignal(
                title="大模型应用开发工程师",
                company="示例科技",
                salary_text="20-35K",
                experience_text="3-5年",
                skills=["RAG", "Agent", "Python"],
                tools=["LangGraph"],
                seniority="mid",
                evidence_ids=["EV-JD-1"],
            )
        ],
        skill_matrix=[
            SkillDemandItem(
                canonical_name="RAG",
                aliases=["RAG"],
                category="ai_model",
                frequency=1,
                seniority_distribution={"mid": 1},
                representative_evidence_ids=["EV-JD-1"],
            )
        ],
        source_coverage=SourceCoverageMatrix(total_evidence=1, uploaded_jd_count=1, skill_signal_count=1),
    )
    return project, knowledge_base
