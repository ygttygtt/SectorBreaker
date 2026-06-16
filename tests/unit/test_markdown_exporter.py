import asyncio
from pathlib import Path

from backend.app.exporters.markdown import MarkdownExporter
from backend.app.graph.workflow import run_research_workflow
from backend.app.schemas import MarketScope, ResearchDepth, ResearchProject


def test_markdown_exporter_writes_obsidian_package(tmp_path: Path) -> None:
    project = ResearchProject(
        id="project-1",
        title="AI Agent Tools",
        domain="AI Agent 工具",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )
    state = asyncio.run(run_research_workflow(project))

    manifest = MarkdownExporter(tmp_path).export_project(project, state.artifacts, state.evidence)

    assert manifest.project_id == "project-1"
    assert (tmp_path / "ai-agent-tools" / "manifest.json").exists()
    assert (tmp_path / "ai-agent-tools" / "00-研究框架" / "research-frame.md").exists()
    content = (tmp_path / "ai-agent-tools" / "05-机会地图" / "opportunity-map.md").read_text(
        encoding="utf-8"
    )
    assert "evidence_ids:" in content
    assert "EV-USER-SCOPE" in content
