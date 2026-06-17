import asyncio
from pathlib import Path

from backend.app.exporters.markdown import MarkdownExporter
from backend.app.graph.workflow import run_research_workflow
from backend.app.providers.fakes import FakeLLMProvider
from backend.app.schemas import MarketScope, ResearchDepth, ResearchProject


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
