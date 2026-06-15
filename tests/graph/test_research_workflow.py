from backend.app.graph.workflow import run_research_workflow
from backend.app.schemas import ArtifactType, MarketScope, ResearchDepth, ResearchGate, ResearchProject


def test_research_workflow_generates_evidence_linked_artifacts() -> None:
    project = ResearchProject(
        id="project-1",
        title="AI Agent Tools",
        domain="AI Agent 工具",
        market_scope=MarketScope.MIXED,
        depth=ResearchDepth.QUICK,
    )

    state = run_research_workflow(project)

    artifact_types = {artifact.artifact_type for artifact in state.artifacts}
    assert state.current_gate == ResearchGate.EXPORT
    assert ArtifactType.RESEARCH_FRAME in artifact_types
    assert ArtifactType.INDUSTRY_MAP in artifact_types
    assert ArtifactType.OPPORTUNITY_MAP in artifact_types
    assert state.evidence[0].id == "EV-USER-SCOPE"
    assert all(artifact.source_evidence_ids for artifact in state.artifacts)

