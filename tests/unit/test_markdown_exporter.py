import asyncio
from pathlib import Path

from backend.app.exporters.markdown import MarkdownExporter
from backend.app.graph.workflow import run_research_workflow
from backend.app.providers.fakes import FakeLLMProvider
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    ClaimStrength,
    EvidenceItem,
    MarketScope,
    ResearchDepth,
    ResearchProject,
    RunEvent,
    SourceChannel,
    SourceQuality,
    VerificationStatus,
)


def _default_fake_llm():
    return FakeLLMProvider(
        response={
            "domain_definition": "测试行业",
            "boundaries": "测试边界",
            "common_confusions": [],
            "key_questions": [],
            "data_caliber": [],
            "sections": ["行业定义"],
            "key_questions_list": [],
            "learning_path": [],
            "title": "测试",
            "content": "# 测试内容\n\n行业分析。",
        }
    )


def test_markdown_exporter_writes_obsidian_package(tmp_path: Path) -> None:
    project = ResearchProject(
        id="project-1",
        title="AI Agent Tools",
        domain="AI Agent 工具",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )
    state = asyncio.run(run_research_workflow(project, llm_provider=_default_fake_llm()))

    manifest = MarkdownExporter(tmp_path).export_project(project, state.artifacts, state.evidence)

    assert manifest.project_id == "project-1"
    assert (tmp_path / "ai-agent-tools" / "manifest.json").exists()
    assert (tmp_path / "ai-agent-tools" / "00-研究框架" / "research-frame.md").exists()
    content = (tmp_path / "ai-agent-tools" / "05-机会与验证" / "00-机会总览.md").read_text(
        encoding="utf-8"
    )
    assert "evidence_ids:" in content
    assert "EV-USER-SCOPE" in content


def test_markdown_exporter_writes_runnable_v1_vault_layout(tmp_path: Path) -> None:
    project = ResearchProject(
        id="project-v1",
        title="Agent Development",
        domain="Agent development",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )
    artifacts = [
        Artifact(
            id=f"ART-V1-{index}",
            project_id=project.id,
            artifact_type=ArtifactType.INDUSTRY_MAP,
            title=path.removesuffix(".md"),
            content_path=path,
            content=f"# {path}\n\nV1 content.",
            source_evidence_ids=["EV-V1-1"],
            schema_version="v1",
        )
        for index, path in enumerate(
            [
                "00-领域总览.md",
                "01-入门路线.md",
                "02-核心概念.md",
                "03-玩家与工具地图.md",
                "04-趋势与证据.md",
                "05-问题与机会.md",
                "99-待验证问题.md",
            ],
            start=1,
        )
    ]
    artifacts.extend([
        Artifact(
            id="ART-V1-CARD-CONCEPT",
            project_id=project.id,
            artifact_type=ArtifactType.CORE_CONCEPTS,
            title="RAG",
            content_path="concepts/RAG.md",
            content="# RAG\n\nConcept card.",
            source_evidence_ids=["EV-V1-1"],
            schema_version="v1-card",
        ),
        Artifact(
            id="ART-V1-CARD-ARCH",
            project_id=project.id,
            artifact_type=ArtifactType.PLAYER_TOOL_MAP,
            title="Agent 工作流",
            content_path="architectures/Agent 工作流.md",
            content="# Agent 工作流\n\nArchitecture card.",
            source_evidence_ids=["EV-V1-1"],
            schema_version="v1-card",
        ),
        Artifact(
            id="ART-V1-CARD-TOOL",
            project_id=project.id,
            artifact_type=ArtifactType.PLAYER_MAP,
            title="LangGraph",
            content_path="tools/LangGraph.md",
            content="# LangGraph\n\nTool card.",
            source_evidence_ids=["EV-V1-1"],
            schema_version="v1-card",
        ),
        Artifact(
            id="ART-V1-CARD-QUESTION",
            project_id=project.id,
            artifact_type=ArtifactType.UNRESOLVED_QUESTIONS,
            title="待验证问题 1 - 评测方式",
            content_path="questions/待验证问题 1 - 评测方式.md",
            content="# 待验证问题 1 - 评测方式\n\nQuestion card.",
            source_evidence_ids=["EV-V1-1"],
            schema_version="v1-card",
        ),
    ])
    evidence = [
        EvidenceItem(
            id="EV-V1-1",
            project_id=project.id,
            source_title="Agent development trend source",
            source_url="https://example.com/agent-development",
            source_type="web",
            source_channel=SourceChannel.SEARCH,
            snippet="Agent development is moving toward tooling, memory, and evaluation.",
            source_quality=SourceQuality.MEDIUM,
            claim_strength=ClaimStrength.FACT,
            confidence=0.7,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        )
    ]

    manifest = MarkdownExporter(tmp_path).export_project(project, artifacts, evidence)

    expected_paths = {
        "00-领域总览.md",
        "01-入门路线.md",
        "02-核心概念.md",
        "03-玩家与工具地图.md",
        "04-趋势与证据.md",
        "05-问题与机会.md",
        "99-待验证问题.md",
        "_sources/evidence-ledger.md",
        "README.md",
        "manifest.json",
    }
    assert expected_paths.issubset(set(manifest.artifact_paths))
    project_dir = tmp_path / "agent-development"
    for relative_path in expected_paths:
        assert (project_dir / relative_path).exists()
    readme = (project_dir / "README.md").read_text(encoding="utf-8")
    assert "知识库首页" in readme
    assert "主文档入口" in readme
    assert "知识卡片入口" in readme
    assert "[[00-领域总览]]" in readme
    assert "[[RAG]]" in readme
    assert "[[Agent 工作流]]" in readme
    assert "[[LangGraph]]" in readme
    assert "[[待验证问题 1 - 评测方式]]" in readme
    assert "如何继续补库" in readme


def test_markdown_exporter_writes_v2_agent_kernel_vault_home_with_cards(tmp_path: Path) -> None:
    project = ResearchProject(
        id="project-v2-kernel-vault",
        title="API中转站",
        domain="API中转站",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )
    artifacts = [
        Artifact(
            id="ART-KERNEL-L1",
            project_id=project.id,
            artifact_type=ArtifactType.DOMAIN_OVERVIEW,
            title="API 中转站：本源与需求",
            content_path="01-API中转站-本源与需求.md",
            content="# API 中转站：本源与需求\n\n## 小节\n\n正文",
            source_evidence_ids=["EV-KERNEL-1"],
            schema_version="v2-agent-kernel",
        ),
        Artifact(
            id="ART-KERNEL-CARD",
            project_id=project.id,
            artifact_type=ArtifactType.CORE_CONCEPTS,
            title="反向代理",
            content_path="concepts/反向代理.md",
            content="# 反向代理\n\n## 小节\n\n正文",
            source_evidence_ids=["EV-KERNEL-1"],
            schema_version="v2-agent-kernel-card",
        ),
        Artifact(
            id="ART-KERNEL-INDEX",
            project_id=project.id,
            artifact_type=ArtifactType.EXPORT_MANIFEST,
            title="API 中转站知识库导航",
            content_path="00-知识库导航.md",
            content="# API 中转站知识库导航\n\n## 推荐阅读顺序\n\n- [[01-API中转站-本源与需求]]\n- [[反向代理]]",
            source_evidence_ids=["EV-KERNEL-1"],
            schema_version="v2-agent-kernel-index",
        ),
    ]
    evidence = [
        EvidenceItem(
            id="EV-KERNEL-1",
            project_id=project.id,
            source_title="API 中转站来源",
            source_url="https://example.com/api-proxy",
            source_type="web",
            source_channel=SourceChannel.SEARCH,
            snippet="API proxy context.",
            source_quality=SourceQuality.MEDIUM,
            claim_strength=ClaimStrength.FACT,
            confidence=0.7,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        )
    ]

    manifest = MarkdownExporter(tmp_path).export_project(project, artifacts, evidence)

    project_dir = tmp_path / "api中转站"
    assert "README.md" in manifest.artifact_paths
    assert "00-知识库导航.md" in manifest.artifact_paths
    assert "concepts/反向代理.md" in manifest.artifact_paths
    readme = (project_dir / "README.md").read_text(encoding="utf-8")
    assert "领域知识库" in readme
    assert "不是一篇一次性报告" in readme
    assert "[[00-知识库导航]]" in readme
    assert "[[01-API中转站-本源与需求]]" in readme
    assert "[[反向代理]]" in readme
    assert "解释性/辅助卡数量：1" in readme
    state = (project_dir / ".sectorbreaker" / "agent_state.json").read_text(encoding="utf-8")
    assert '"artifact_count": 3' in state


def test_markdown_exporter_copies_default_obsidian_config(tmp_path: Path) -> None:
    project = ResearchProject(
        id="project-vault-config",
        title="Vault Config Demo",
        domain="Vault Config Demo",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )
    artifact = Artifact(
        id="ART-DEMO",
        project_id=project.id,
        artifact_type=ArtifactType.DOMAIN_OVERVIEW,
        title="领域总览",
        content_path="00-领域总览.md",
        content="# 领域总览\n\nDemo.",
        source_evidence_ids=[],
        schema_version="v1",
    )

    MarkdownExporter(tmp_path).export_project(project, [artifact], [])

    project_dir = tmp_path / "vault-config-demo"
    assert (project_dir / ".obsidian" / "app.json").exists()
    assert (project_dir / ".obsidian" / "core-plugins.json").exists()


def test_markdown_exporter_writes_sectorbreaker_state_bundle(tmp_path: Path) -> None:
    project = ResearchProject(
        id="project-living-vault",
        title="Living Vault Demo",
        domain="Living Vault Demo",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )
    artifact = Artifact(
        id="ART-FOLLOWUP-1",
        project_id=project.id,
        artifact_type=ArtifactType.FOLLOW_UP_NOTE,
        title="追问：反向代理是什么",
        content_path="followups/20260707-reverse-proxy.md",
        content="# 反向代理是什么\n\n基于项目资料的补库回答。",
        source_evidence_ids=["EV-LIVING-1"],
        schema_version="living-vault-followup-v1",
    )
    evidence = [
        EvidenceItem(
            id="EV-LIVING-1",
            project_id=project.id,
            source_title="Living source",
            source_url="https://example.com/living",
            source_type="web",
            source_channel=SourceChannel.SEARCH,
            snippet="Reverse proxy context.",
            source_quality=SourceQuality.MEDIUM,
            claim_strength=ClaimStrength.FACT,
            confidence=0.7,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        )
    ]

    manifest = MarkdownExporter(tmp_path).export_project(
        project,
        [artifact],
        evidence,
        run_events=[RunEvent(event_type="artifact_created", gate="human_feedback", message="已根据追问补库")],
    )

    project_dir = tmp_path / "living-vault-demo"
    assert ".sectorbreaker/project.json" in manifest.artifact_paths
    assert ".sectorbreaker/agent_state.json" in manifest.artifact_paths
    assert ".sectorbreaker/evidence_ledger.json" in manifest.artifact_paths
    assert ".sectorbreaker/artifact_manifest.json" in manifest.artifact_paths
    assert ".sectorbreaker/trace_summary.json" in manifest.artifact_paths
    state = (project_dir / ".sectorbreaker" / "agent_state.json").read_text(encoding="utf-8")
    assert '"followup_count": 1' in state
    trace = (project_dir / ".sectorbreaker" / "trace_summary.json").read_text(encoding="utf-8")
    assert "已根据追问补库" in trace
