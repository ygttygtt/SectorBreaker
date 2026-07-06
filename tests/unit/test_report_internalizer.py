from backend.app.agent_state.models import SectorBreakerState, TrustLevel
from backend.app.agent_state.report_internalizer import ReportInternalizer
from backend.app.schemas.documents import ProjectDocument


def test_report_internalizer_extracts_low_trust_claims_entities_and_questions() -> None:
    document = ProjectDocument(
        id="doc-1",
        project_id="p1",
        channel="assistant_brief",
        file_name="gemini-deepsearch.md",
        content=(
            "Gemini 报告认为“大模型 API 中转站”需求来自官方充值门槛和访问限制。"
            "主流工具包括 New-API 和 One API。"
            "商业模式可能包括套餐分销和价格差。"
            "但账号来源是否稳定仍待验证？"
            "参考：https://example.com/report"
        ),
        char_count=120,
        citation_count=1,
    )

    result = ReportInternalizer().internalize(document, domain="大模型 API 中转站")

    assert result.citation_urls == ["https://example.com/report"]
    assert result.claims
    assert result.entities
    assert result.open_questions
    assert all(claim.trust_level == TrustLevel.LOW for claim in result.claims)
    assert any("New-API" in entity.name for entity in result.entities)


def test_report_internalizer_applies_memory_to_state() -> None:
    state = SectorBreakerState.initialize(project_id="p1", domain="量化投资", user_goal="生成知识库")
    document = ProjectDocument(
        id="doc-2",
        project_id="p1",
        channel="assistant_brief",
        file_name="deepsearch.txt",
        content="量化投资需要理解股票、回测、滑点和风险控制。股票是什么仍需要前置扫盲？",
        char_count=42,
    )
    internalizer = ReportInternalizer()
    report = internalizer.internalize(document, domain="量化投资")

    internalizer.apply_to_state(state, report)

    assert state.shared_knowledge.source_memories[0].source_id == "doc-2"
    assert state.shared_knowledge.claims
    assert state.shared_knowledge.open_questions
    assert "DOC-doc-2" in state.evidence_refs
