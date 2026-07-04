from backend.app.talent_demand.models import (
    JobPostingSignal,
    SourceCoverageMatrix,
    TalentDemandInput,
    TalentDemandKnowledgeBase,
)


def test_talent_demand_models_have_safe_defaults() -> None:
    input_model = TalentDemandInput(target_role="大模型应用开发工程师")
    posting = JobPostingSignal(title="大模型应用开发工程师", evidence_ids=["EV-JD-1"])
    coverage = SourceCoverageMatrix()
    knowledge_base = TalentDemandKnowledgeBase(postings=[posting], source_coverage=coverage)

    assert input_model.market_scope == "mixed"
    assert input_model.purpose == "market_research"
    assert posting.salary_text is None
    assert posting.experience_text is None
    assert posting.skills == []
    assert posting.evidence_ids == ["EV-JD-1"]
    assert coverage.total_evidence == 0
    assert coverage.gaps == []
    assert knowledge_base.skill_matrix == []


def test_talent_demand_models_round_trip_as_json() -> None:
    knowledge_base = TalentDemandKnowledgeBase(
        overview="样本来自用户上传 JD。",
        postings=[
            JobPostingSignal(
                title="AI Agent 工程师",
                salary_text="20-35K",
                experience_text="3-5 年",
                skills=["Python", "LangGraph"],
                evidence_ids=["EV-JD-1"],
                confidence=0.7,
            )
        ],
        source_coverage=SourceCoverageMatrix(total_evidence=1, salary_signal_count=1),
    )

    payload = knowledge_base.model_dump(mode="json")
    restored = TalentDemandKnowledgeBase.model_validate(payload)

    assert restored.postings[0].title == "AI Agent 工程师"
    assert restored.postings[0].evidence_ids == ["EV-JD-1"]
    assert restored.source_coverage.salary_signal_count == 1
