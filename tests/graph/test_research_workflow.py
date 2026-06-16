import asyncio

from backend.app.graph.workflow import run_research_workflow
from backend.app.providers.fakes import FakeLLMProvider, FakeSearchProvider
from backend.app.schemas import ArtifactType, MarketScope, ResearchDepth, ResearchGate, ResearchProject


def _default_fake_llm():
    return FakeLLMProvider(
        response={
            "domain_definition": "测试行业",
            "boundaries": "测试边界",
            "common_confusions": ["测试混淆"],
            "key_questions": [{"question": "测试问题", "importance": "重要", "source": "搜索", "common_mistake": "无", "priority_1h": "高"}],
            "data_caliber": [],
            "sections": ["行业定义", "市场现状"],
            "key_questions_list": ["用户为什么付费？"],
            "learning_path": ["先学行业定义"],
            "title": "测试产物",
            "content": "# 测试内容\n\n行业边界和市场现状分析。",
        }
    )


def test_research_workflow_generates_evidence_linked_artifacts() -> None:
    project = ResearchProject(
        id="project-1",
        title="AI Agent Tools",
        domain="AI Agent 工具",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )

    state = asyncio.run(run_research_workflow(project, llm_provider=_default_fake_llm()))

    artifact_types = {artifact.artifact_type for artifact in state.artifacts}
    assert state.current_gate == ResearchGate.EXPORT
    assert ArtifactType.RESEARCH_FRAME in artifact_types
    assert ArtifactType.INDUSTRY_MAP in artifact_types
    assert ArtifactType.OPPORTUNITY_MAP in artifact_types
    assert state.evidence[0].id == "EV-USER-SCOPE"
    assert all(artifact.source_evidence_ids for artifact in state.artifacts)


def test_research_workflow_uses_search_and_llm_providers() -> None:
    project = ResearchProject(
        id="project-2",
        title="Pet Services",
        domain="宠物服务",
        market_scope=MarketScope.CHINA,
        depth=ResearchDepth.STANDARD,
    )
    search_provider = FakeSearchProvider(
        results=[
            {
                "title": "宠物服务市场",
                "url": "https://example.com/pet-services",
                "snippet": "宠物服务需求增长，细分场景包括寄养、医疗和殡葬。",
            }
        ]
    )
    llm_provider = FakeLLMProvider(
        response={
            "sections": ["行业边界", "市场现状", "交易单位"],
            "key_questions": ["用户为什么付费？", "信任资产是什么？"],
        }
    )

    state = asyncio.run(run_research_workflow(project, search_provider=search_provider, llm_provider=llm_provider))

    artifact_types = {artifact.artifact_type for artifact in state.artifacts}
    assert "宠物服务市场" in state.evidence[1].source_title
    assert ArtifactType.MARKET_OVERVIEW in artifact_types
    assert ArtifactType.PLAYER_MAP in artifact_types
    assert ArtifactType.CONTENT_CHANNELS in artifact_types
    # Find the research frame artifact (may not be first due to scope analysis)
    research_frame = next(a for a in state.artifacts if a.id == "ART-RESEARCH-FRAME")
    assert "行业边界" in research_frame.content


def test_research_workflow_blocks_export_when_research_frame_is_empty() -> None:
    project = ResearchProject(
        id="project-3",
        title="Weak Planner",
        domain="低质量规划",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )
    llm_provider = FakeLLMProvider(response={"sections": [], "key_questions": []})

    state = asyncio.run(run_research_workflow(project, llm_provider=llm_provider))

    assert state.current_gate == ResearchGate.OPPORTUNITY
    assert state.coverage_checklist["research_frame"] is False
    assert any("研究框架" in issue for issue in state.qa_issues)
