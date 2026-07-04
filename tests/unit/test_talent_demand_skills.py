from backend.app.talent_demand.models import JobPostingSignal
from backend.app.talent_demand.skills import build_skill_matrix, normalize_skill_name


def test_normalizes_required_ai_skill_aliases() -> None:
    assert normalize_skill_name("大模型") == "LLM"
    assert normalize_skill_name("llm") == "LLM"
    assert normalize_skill_name("Agent") == "Agent"
    assert normalize_skill_name("智能体") == "Agent"
    assert normalize_skill_name("向量库") == "向量数据库"


def test_build_skill_matrix_merges_aliases_and_counts_frequency() -> None:
    postings = [
        JobPostingSignal(
            title="大模型应用开发工程师",
            skills=["大模型", "RAG", "Python", "向量库"],
            tools=["LangChain"],
            seniority="mid",
            evidence_ids=["EV-JD-1"],
        ),
        JobPostingSignal(
            title="AI Agent 工程师",
            skills=["LLM", "检索增强生成", "python", "向量数据库"],
            tools=["LangGraph", "FastAPI"],
            seniority="senior",
            evidence_ids=["EV-JD-2"],
        ),
    ]

    matrix = build_skill_matrix(postings)
    by_name = {item.canonical_name: item for item in matrix}

    assert by_name["LLM"].frequency == 2
    assert by_name["RAG"].frequency == 2
    assert by_name["Python"].frequency == 2
    assert by_name["向量数据库"].frequency == 2
    assert by_name["LLM"].seniority_distribution == {"mid": 1, "senior": 1}
    assert by_name["LangGraph"].category == "framework"
    assert by_name["FastAPI"].category == "backend"
    assert by_name["RAG"].representative_evidence_ids == ["EV-JD-1", "EV-JD-2"]
