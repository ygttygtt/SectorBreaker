from backend.app.talent_demand.extraction import extract_job_posting_signals_from_text


def test_extracts_conservative_chinese_jd_signals_with_evidence_id() -> None:
    text = """
    岗位：大模型应用开发工程师
    公司：示例科技
    地点：北京
    薪资：20-35K·14薪
    经验要求：3-5年
    学历要求：本科及以上
    职责：
    1. 负责 RAG 知识库和 Agent 应用开发。
    2. 使用 LangChain、LangGraph、FastAPI 构建生产服务。
    要求：熟悉 Python、向量数据库和 LLM API。
    """

    postings = extract_job_posting_signals_from_text(text, evidence_id="EV-JD-1")

    assert len(postings) == 1
    posting = postings[0]
    assert posting.title == "大模型应用开发工程师"
    assert posting.company == "示例科技"
    assert posting.location == "北京"
    assert posting.salary_text == "20-35K·14薪"
    assert posting.experience_text == "3-5年"
    assert posting.education_text == "本科及以上"
    assert posting.evidence_ids == ["EV-JD-1"]
    assert "Python" in posting.skills
    assert "RAG" in posting.skills
    assert "LangGraph" in posting.tools
    assert posting.seniority == "mid"


def test_missing_fields_remain_empty_or_none() -> None:
    postings = extract_job_posting_signals_from_text(
        "我们正在招聘 AI 方向工程师，参与内部知识库建设。",
        evidence_id="EV-THIN-1",
    )

    assert len(postings) == 1
    posting = postings[0]
    assert posting.title == "AI 方向工程师"
    assert posting.company is None
    assert posting.salary_text is None
    assert posting.experience_text is None
    assert posting.education_text is None
    assert posting.skills == []
    assert posting.tools == []
    assert posting.evidence_ids == ["EV-THIN-1"]


def test_experience_number_is_not_treated_as_salary() -> None:
    postings = extract_job_posting_signals_from_text(
        """
        岗位：Python 后端工程师
        经验要求：3年
        要求：熟悉 FastAPI。
        """,
        evidence_id="EV-JD-2",
    )

    assert postings[0].salary_text is None
    assert postings[0].experience_text == "3年"
