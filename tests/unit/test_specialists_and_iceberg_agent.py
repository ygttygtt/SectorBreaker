from backend.app.agent_state.models import KnowledgeLayerId
from backend.app.agents.iceberg_agent import IcebergRiskAgent
from backend.app.agents.specialists import SpecialistTaskPlanner, default_specialist_specs


def test_default_specialists_cover_l1_to_l5() -> None:
    specs = default_specialist_specs()
    layer_ids = {spec.layer_id for spec in specs}

    assert KnowledgeLayerId.WHAT_WHY in layer_ids
    assert KnowledgeLayerId.WHO in layer_ids
    assert KnowledgeLayerId.HOW in layer_ids
    assert KnowledgeLayerId.MONEY in layer_ids
    assert KnowledgeLayerId.RISKS in layer_ids
    assert all("任务：" in spec.system_brief() and "完成判断：" in spec.system_brief() for spec in specs)
    assert any(spec.agent_id == "l5_risk_agent" and spec.safety_notes for spec in specs)


def test_iceberg_agent_builds_seed_queries_and_redacts_operational_details() -> None:
    agent = IcebergRiskAgent()
    plan = agent.build_seed_plan("留学")

    assert any("骗局" in query for query in plan.seed_queries)
    assert any("监管" in query for query in plan.seed_queries)

    text = "文章提到“保录取”、背景提升造假、接码平台和批量注册教程。"
    findings = agent.extract_risk_terms(text, domain="留学")
    redacted = agent.redact_operational_detail(text)

    assert any(finding.term == "保录取" for finding in findings)
    assert any(not finding.allowed_for_output for finding in findings)
    assert "批量注册教程" not in redacted
    assert "已移除" in redacted

    source_memories, claims, questions = agent.findings_to_state_objects(domain="留学", findings=findings)
    assert source_memories
    assert claims
    assert questions
    assert all(claim.needs_verification for claim in claims)
    assert any("风险" in question.question for question in questions)


def test_specialist_task_planner_creates_follow_up_for_unknown_terms() -> None:
    planner = SpecialistTaskPlanner()

    tasks = planner.discover_follow_up_tasks(
        domain="大模型 API 中转站",
        layer_id=KnowledgeLayerId.HOW,
        observations=["搭建中转站时资料反复提到号池、接码平台和指纹浏览器，但没有解释原理。"],
    )

    titles = [task.title for task in tasks]
    assert any("号池" in title for title in titles)
    assert any("接码" in title for title in titles)
    assert all(task.layer_id == KnowledgeLayerId.HOW for task in tasks)
    assert any("原理" in query for task in tasks for query in task.suggested_queries)
