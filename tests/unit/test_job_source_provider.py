import asyncio
import json
import sys
from pathlib import Path

from backend.app.providers.interfaces import JobSourceQuery
from backend.app.providers.job_sources import BossAgentCliProvider, DisabledJobSourceProvider


def test_disabled_job_source_provider_reports_unavailable() -> None:
    provider = DisabledJobSourceProvider()

    status = asyncio.run(provider.status())
    jobs = asyncio.run(provider.search_jobs(JobSourceQuery(keyword="AI Agent 工程师")))

    assert status.configured is False
    assert status.available is False
    assert jobs == []


def test_boss_agent_cli_provider_maps_json_array(tmp_path: Path) -> None:
    script = tmp_path / "fake_boss_cli.py"
    script.write_text(
        "import json\n"
        "print(json.dumps([{'title':'AI Agent 工程师','company':'示例科技','city':'北京','salary':'25-40K','experience':'3-5年','skills':['Python','LangGraph'],'url':'https://example.com/job'}], ensure_ascii=False))\n",
        encoding="utf-8",
    )
    provider = BossAgentCliProvider(command=sys.executable, args_template=f"{sys.executable} {script}")

    jobs = asyncio.run(provider.search_jobs(JobSourceQuery(keyword="AI Agent 工程师", city="北京", limit=3)))

    assert len(jobs) == 1
    assert jobs[0].title == "AI Agent 工程师"
    assert jobs[0].company == "示例科技"
    assert jobs[0].location == "北京"
    assert jobs[0].skills == ["Python", "LangGraph"]


def test_boss_agent_cli_provider_maps_jsonl(tmp_path: Path) -> None:
    script = tmp_path / "fake_boss_cli_jsonl.py"
    rows = [
        {"job_title": "RAG 工程师", "company_name": "知识库公司", "location": "上海"},
        {"positionName": "LLM 应用开发", "brandName": "模型公司", "salaryDesc": "30-50K"},
    ]
    script.write_text(
        "import json\n"
        + "\n".join(f"print({json.dumps(json.dumps(row, ensure_ascii=False))})" for row in rows),
        encoding="utf-8",
    )
    provider = BossAgentCliProvider(command=sys.executable, args_template=f"{sys.executable} {script}")

    jobs = asyncio.run(provider.search_jobs(JobSourceQuery(keyword="RAG", limit=2)))

    assert [job.title for job in jobs] == ["RAG 工程师", "LLM 应用开发"]
    assert jobs[1].company == "模型公司"
    assert jobs[1].salary_text == "30-50K"


def test_boss_agent_cli_provider_failure_returns_empty() -> None:
    provider = BossAgentCliProvider(command="definitely-not-a-real-boss-command")

    jobs = asyncio.run(provider.search_jobs(JobSourceQuery(keyword="AI Agent 工程师")))

    assert jobs == []

