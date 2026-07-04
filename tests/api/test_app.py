import os
import time
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.providers.fakes import FakeContentExtractionProvider, FakeLLMProvider, FakeSearchProvider
from backend.app.providers.interfaces import JobPostingSource, JobSourceQuery, JobSourceStatus


def _docx_bytes(paragraphs: list[str]) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _wait_for_run(client: TestClient, run_id: str, timeout: float = 10.0) -> dict:
    """Poll until the background run completes or fails."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        status = resp.json()["status"]
        if status in ("completed", "failed"):
            return resp.json()
        time.sleep(0.1)
    raise TimeoutError(f"Run {run_id} did not complete within {timeout}s")


def _default_fake_llm():
    """FakeLLMProvider that returns valid data for any prompt."""
    return FakeLLMProvider(
        response={
            "domain_definition": "测试行业",
            "boundaries": "测试边界",
            "common_confusions": ["测试混淆"],
            "key_questions": [{"question": "测试问题", "importance": "重要", "source": "搜索", "common_mistake": "无", "priority_1h": "高"}],
            "data_caliber": [{"metric": "市场规模", "caliber": "统一口径", "confusion": "无", "suitable_for": "概况", "not_suitable_for": "细节", "recommended_source": "行业报告"}],
            "sections": ["行业定义", "市场现状"],
            "key_questions_list": ["用户为什么付费？"],
            "learning_path": ["先学行业定义"],
            "title": "测试产物",
            "content": "# 测试内容\n\n行业边界和市场现状分析。",
        }
    )


class FakeJobSourceProvider:
    def __init__(self, jobs: list[JobPostingSource], available: bool = True) -> None:
        self.jobs = jobs
        self.available = available
        self.requests: list[JobSourceQuery] = []

    async def status(self) -> JobSourceStatus:
        return JobSourceStatus(
            provider="fake_boss",
            configured=True,
            available=self.available,
            message="fake boss ready" if self.available else "fake boss unavailable",
        )

    async def search_jobs(self, query: JobSourceQuery) -> list[JobPostingSource]:
        self.requests.append(query)
        return self.jobs[: query.limit]


def test_api_runs_research_and_exports_markdown(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    project_response = client.post(
        "/api/projects",
        json={
            "title": "AI Agent Tools",
            "domain": "AI Agent 工具",
            "market_scope": "mixed",
            "depth": "quick",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    run_response = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    assert run_response.status_code == 200
    run_id = run_response.json()["id"]
    assert run_response.json()["status"] == "running"

    # Wait for background workflow to finish
    run_result = _wait_for_run(client, run_id)
    assert run_result["status"] == "completed"

    artifacts_response = client.get(f"/api/projects/{project_id}/artifacts")
    assert artifacts_response.status_code == 200
    assert len(artifacts_response.json()) >= 3

    export_response = client.post(f"/api/projects/{project_id}/exports")
    assert export_response.status_code == 200
    assert export_response.json()["project_id"] == project_id
    assert Path(export_response.json()["export_dir"]).exists()

    list_response = client.get("/api/projects")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == project_id

    detail_response = client.get(f"/api/projects/{project_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["domain"] == "AI Agent 工具"
    assert detail_response.json()["project_mode"] == "domain_knowledge"


def test_api_opens_export_folder_inside_export_root(tmp_path: Path, monkeypatch) -> None:
    opened: list[Path] = []

    def fake_open(path: Path) -> None:
        opened.append(path)

    monkeypatch.setattr("backend.app.api.app._open_local_folder", fake_open)
    export_root = tmp_path / "exports"
    export_dir = export_root / "demo"
    export_dir.mkdir(parents=True)
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=export_root,
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post("/api/exports/open-folder", json={"export_dir": str(export_dir)})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert opened == [export_dir.resolve()]


def test_api_rejects_opening_folder_outside_export_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("backend.app.api.app._open_local_folder", lambda path: None)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post("/api/exports/open-folder", json={"export_dir": str(outside_dir)})

    assert response.status_code == 400


def test_api_accepts_talent_demand_project_mode(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    project_response = client.post(
        "/api/projects",
        json={
            "title": "大模型应用开发工程师需求",
            "domain": "大模型应用开发工程师",
            "market_scope": "china",
            "depth": "quick",
            "source_policy": "reliable_first",
            "project_mode": "talent_demand",
        },
    )

    assert project_response.status_code == 200
    assert project_response.json()["project_mode"] == "talent_demand"

    detail_response = client.get(f"/api/projects/{project_response.json()['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["project_mode"] == "talent_demand"


def test_api_talent_demand_run_uses_uploaded_jd_and_creates_talent_artifacts(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project = client.post(
        "/api/projects",
        json={
            "title": "大模型应用开发工程师需求",
            "domain": "大模型应用开发工程师",
            "market_scope": "china",
            "depth": "quick",
            "source_policy": "reliable_first",
            "project_mode": "talent_demand",
        },
    ).json()
    document_response = client.post(
        f"/api/projects/{project['id']}/documents",
        json={
            "channel": "user_upload",
            "file_name": "jd.md",
            "mime_type": "text/markdown",
            "content": (
                "岗位：大模型应用开发工程师\n"
                "公司：示例科技\n"
                "地点：北京\n"
                "薪资：20-35K·14薪\n"
                "经验要求：3-5年\n"
                "职责：\n"
                "1. 负责 RAG 知识库和 Agent 应用开发。\n"
                "要求：熟悉 Python、LangGraph、FastAPI 和向量数据库。"
            ),
        },
    )
    assert document_response.status_code == 200

    run_response = client.post(f"/api/projects/{project['id']}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    assert run_result["status"] == "completed"
    artifacts = client.get(f"/api/projects/{project['id']}/artifacts").json()
    paths = {artifact["content_path"] for artifact in artifacts}
    assert "00-岗位需求总览.md" in paths
    assert "02-技能需求矩阵.md" in paths
    assert "skills/RAG.md" in paths

    events = client.get(f"/api/runs/{run_response.json()['id']}/events").text
    assert "Talent Source Scout" in events
    assert "Source Coverage" in events


def test_api_project_chat_uses_local_fts(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Pet Services",
            "domain": "宠物服务",
            "market_scope": "china",
            "depth": "quick",
        },
    ).json()["id"]

    run_resp = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    _wait_for_run(client, run_resp.json()["id"])

    chat_response = client.post(f"/api/projects/{project_id}/chat", json={"question": "应该先学什么"})

    assert chat_response.status_code == 200
    assert chat_response.json()["citations"]
    assert chat_response.json()["citation_details"]


def test_api_chat_uses_project_retrieval(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=None,
        )
    )
    project = client.post(
        "/api/projects",
        json={
            "title": "人才需求",
            "domain": "AI Agent 工程师",
            "market_scope": "china",
            "depth": "quick",
            "project_mode": "talent_demand",
        },
    ).json()
    document = client.post(
        f"/api/projects/{project['id']}/documents",
        json={
            "channel": "user_upload",
            "file_name": "jd.md",
            "mime_type": "text/markdown",
            "content": "岗位：AI Agent 工程师\n要求：熟悉 RAG、向量数据库、LangGraph 和 Python。",
        },
    )
    assert document.status_code == 200
    run_response = client.post(f"/api/projects/{project['id']}/runs", params={"auto_run": "true"})
    _wait_for_run(client, run_response.json()["id"])

    chat_response = client.post(f"/api/projects/{project['id']}/chat", json={"question": "RAG 有什么要求"})

    body = chat_response.json()
    assert chat_response.status_code == 200
    assert "RAG" in body["answer"]
    assert body["citations"]
    assert body["citation_details"][0]["source_id"] in body["citations"]


def test_api_talent_demand_run_uses_boss_job_source_when_enabled(tmp_path: Path) -> None:
    job_provider = FakeJobSourceProvider([
        JobPostingSource(
            title="AI Agent 工程师",
            company="示例科技",
            location="北京",
            salary_text="25-40K",
            experience_text="3-5年",
            description="负责 RAG、Agent、LangGraph 和 Python 后端开发。",
            skills=["RAG", "Agent", "LangGraph", "Python"],
            url="https://example.com/boss-job",
        )
    ])
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            job_source_provider=job_provider,
            search_provider=FakeSearchProvider(results=[]),
            llm_provider=None,
        )
    )
    config_response = client.post(
        "/api/config/job-source",
        json={
            "enabled": True,
            "provider": "boss_agent_cli",
            "boss_keyword": "AI Agent 工程师",
            "boss_city": "北京",
            "boss_limit": 3,
        },
    )
    assert config_response.status_code == 200
    project = client.post(
        "/api/projects",
        json={
            "title": "AI Agent 工程师需求",
            "domain": "AI Agent 工程师",
            "market_scope": "china",
            "depth": "quick",
            "project_mode": "talent_demand",
        },
    ).json()

    run_response = client.post(f"/api/projects/{project['id']}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])
    evidence = client.get(f"/api/projects/{project['id']}/evidence").json()

    assert run_result["status"] == "completed"
    assert job_provider.requests
    assert any(item["source_channel"] == "boss_job" for item in evidence)


def test_api_run_uses_injected_search_and_llm_providers(tmp_path: Path) -> None:
    search_provider = FakeSearchProvider(
        results=[
            {
                "title": "宠物服务市场",
                "url": "https://example.com/pet-services",
                "snippet": "宠物服务需求增长。",
            }
        ]
    )
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=search_provider,
            llm_provider=FakeLLMProvider(
                response={
                    "sections": ["行业边界", "市场现状"],
                    "key_questions": ["谁付钱？"],
                }
            ),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Pet Services",
            "domain": "宠物服务",
            "market_scope": "china",
            "depth": "quick",
        },
    ).json()["id"]

    run_response = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    run_id = run_response.json()["id"]
    run_result = _wait_for_run(client, run_id)
    assert run_result["status"] == "completed"

    evidence_response = client.get(f"/api/projects/{project_id}/evidence")
    assert evidence_response.json()[1]["source_title"] == "宠物服务市场"
    assert search_provider.search_requests


def test_api_run_applies_source_policy_domain_constraints(tmp_path: Path) -> None:
    search_provider = FakeSearchProvider(
        results=[
            {
                "title": "官方政策信息",
                "url": "https://example.org/policy",
                "snippet": "政策环境和监管要求。",
            }
        ]
    )
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=search_provider,
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "政策机会",
            "domain": "政策机会",
            "market_scope": "china",
            "depth": "quick",
            "source_policy": "reliable_only",
        },
    ).json()["id"]

    run_response = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    assert run_result["status"] == "completed"
    assert search_provider.search_requests
    first_request = search_provider.search_requests[0]
    assert first_request.allowed_domains
    assert "gov.cn" in first_request.allowed_domains
    assert "medium.com" in (first_request.blocked_domains or [])


def test_api_exposes_workflow_definition_and_source_policy(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project = client.post(
        "/api/projects",
        json={
            "title": "政策机会",
            "domain": "政策机会",
            "market_scope": "china",
            "depth": "quick",
            "source_policy": "reliable_only",
        },
    ).json()

    assert project["source_policy"] == "reliable_only"

    definition = client.get(f"/api/projects/{project['id']}/workflow-definition")
    assert definition.status_code == 200
    node_ids = {node["id"] for node in definition.json()["nodes"]}
    assert "master_agent" in node_ids
    assert "source_collection" in node_ids
    assert "coverage_evaluation" in node_ids
    assert "knowledge_structuring" in node_ids
    assert "evidence_ledger" in node_ids


def test_api_exposes_search_config_status(tmp_path: Path) -> None:
    os.environ.pop("SEARCH_PROVIDER_MODE", None)
    os.environ.pop("TAVILY_API_KEY", None)
    os.environ.pop("SERPER_API_KEY", None)
    os.environ.pop("BRAVE_API_KEY", None)
    os.environ.pop("EXA_API_KEY", None)
    os.environ.pop("CONTENT_EXTRACTION_PROVIDER", None)
    os.environ.pop("FIRECRAWL_API_KEY", None)
    os.environ.pop("JINA_READER_ENDPOINT_PREFIX", None)
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.get("/api/config/search")

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "provider": None,
        "providers": [],
        "requested_provider_mode": "auto",
        "extraction_provider": "http",
        "extraction_providers": ["http"],
        "requested_extraction_provider": "http",
        "missing_configuration": ["tavily_api_key", "serper_api_key", "brave_api_key", "exa_api_key"],
        "diagnostics": ["至少需要配置 Tavily、Serper、Brave、Exa 四者之一的 API Key，开放网络搜索才会启用。"],
        "status_message": "搜索未配置：请至少填写 Tavily、Serper、Brave、Exa 四者之一的 API Key。",
    }

    configured_client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker-configured.sqlite3",
            export_root=tmp_path / "exports-configured",
            search_provider=FakeSearchProvider(results=[]),
            llm_provider=_default_fake_llm(),
        )
    )

    configured_response = configured_client.get("/api/config/search")

    assert configured_response.status_code == 200
    assert configured_response.json()["configured"] is True
    assert configured_response.json()["providers"]
    assert configured_response.json()["extraction_providers"]
    assert "status_message" in configured_response.json()


def test_api_search_status_only_reports_missing_key_for_forced_provider_mode(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "exa",
            "tavily_api_key": "",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "exa-test-key",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_provider_mode"] == "exa"
    assert status.json()["missing_configuration"] == []


def test_api_search_status_reports_only_selected_provider_missing_key_when_forced_mode_unconfigured(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "exa",
            "tavily_api_key": "tvly-test-key",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is False
    assert status.json()["requested_provider_mode"] == "exa"
    assert status.json()["missing_configuration"] == ["exa_api_key"]


def test_api_tests_search_and_content_extraction_chain(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=FakeSearchProvider(
                results=[
                    {
                        "title": "Official market report",
                        "url": "https://example.org/report",
                        "snippet": "Official statistics and market overview.",
                    }
                ]
            ),
            content_extraction_provider=FakeContentExtractionProvider(
                pages={
                    "https://example.org/report": {
                        "title": "Official Market Report",
                        "raw_text": "Official market report body content.",
                        "domain": "example.org",
                    }
                }
            ),
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search/test",
        json={
            "query": "AI agent market",
            "market_scope": "mixed",
            "max_results": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["result_count"] == 1
    assert response.json()["results"][0]["title"] == "Official market report"
    assert response.json()["extracted_page"]["title"] == "Official Market Report"
    assert response.json()["source_assessment"]["source_quality"] in {"high", "medium", "low", "unknown"}


def test_api_search_test_accepts_domain_filters(tmp_path: Path) -> None:
    captured_queries: list = []

    class CaptureSearchProvider(FakeSearchProvider):
        async def search(self, query):
            captured_queries.append(query)
            return await super().search(query)

    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=CaptureSearchProvider(
                results=[
                    {
                        "title": "Official market report",
                        "url": "https://example.org/report",
                        "snippet": "Official statistics and market overview.",
                    }
                ]
            ),
            content_extraction_provider=FakeContentExtractionProvider(
                pages={
                    "https://example.org/report": {
                        "title": "Official Market Report",
                        "raw_text": "Official market report body content.",
                        "domain": "example.org",
                    }
                }
            ),
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search/test",
        json={
            "query": "AI agent market",
            "market_scope": "mixed",
            "max_results": 2,
            "allowed_domains": ["sec.gov"],
            "blocked_domains": ["medium.com"],
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["source_policy"] == "open_web"
    assert response.json()["effective_allowed_domains"] == ["sec.gov"]
    assert response.json()["effective_blocked_domains"] == ["medium.com"]
    assert captured_queries
    assert captured_queries[0].allowed_domains == ["sec.gov"]
    assert captured_queries[0].blocked_domains == ["medium.com"]


def test_api_search_test_applies_source_policy_constraints(tmp_path: Path) -> None:
    captured_queries: list = []

    class CaptureSearchProvider(FakeSearchProvider):
        async def search(self, query):
            captured_queries.append(query)
            return await super().search(query)

    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=CaptureSearchProvider(
                results=[
                    {
                        "title": "Official market report",
                        "url": "https://example.org/report",
                        "snippet": "Official statistics and market overview.",
                    }
                ]
            ),
            content_extraction_provider=FakeContentExtractionProvider(
                pages={
                    "https://example.org/report": {
                        "title": "Official Market Report",
                        "raw_text": "Official market report body content.",
                        "domain": "example.org",
                    }
                }
            ),
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search/test",
        json={
            "query": "AI agent market",
            "market_scope": "china",
            "source_policy": "reliable_only",
            "max_results": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["source_policy"] == "reliable_only"
    assert "gov.cn" in response.json()["effective_allowed_domains"]
    assert "medium.com" in response.json()["effective_blocked_domains"]
    assert captured_queries
    assert "gov.cn" in (captured_queries[0].allowed_domains or [])
    assert "medium.com" in (captured_queries[0].blocked_domains or [])


def test_api_updates_search_runtime_config(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "auto",
            "tavily_api_key": "tvly-test-key",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "jina",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert "tavily" in status.json()["providers"]
    assert status.json()["requested_provider_mode"] == "auto"
    assert "jinareader" in status.json()["extraction_providers"]
    assert status.json()["requested_extraction_provider"] == "jina"


def test_api_search_status_reports_firecrawl_fallback_diagnostics(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "auto",
            "tavily_api_key": "tvly-test-key",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "firecrawl",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_extraction_provider"] == "firecrawl"
    assert status.json()["extraction_provider"] == "http"
    assert "firecrawl_api_key" in status.json()["missing_configuration"]
    assert any("Firecrawl" in item for item in status.json()["diagnostics"])


def test_api_updates_search_runtime_config_with_brave_provider(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "brave",
            "tavily_api_key": "",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "brave-test-key",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_provider_mode"] == "brave"
    assert "brave" in status.json()["providers"]


def test_api_updates_search_runtime_config_with_explicit_multi_mode(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "multi",
            "tavily_api_key": "tvly-test-key",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "serper-test-key",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_provider_mode"] == "multi"
    assert "tavily" in status.json()["providers"]
    assert "serper" in status.json()["providers"]


def test_api_restores_persisted_search_runtime_config_after_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    export_root = tmp_path / "exports"

    first_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
            llm_provider=_default_fake_llm(),
        )
    )

    save_response = first_client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "brave",
            "tavily_api_key": "",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "brave-test-key",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert save_response.status_code == 200

    restarted_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
            llm_provider=_default_fake_llm(),
        )
    )

    status = restarted_client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_provider_mode"] == "brave"
    assert "brave" in status.json()["providers"]


def test_api_restores_persisted_llm_runtime_config_after_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    export_root = tmp_path / "exports"

    first_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
        )
    )

    save_response = first_client.post(
        "/api/config/llm",
        json={
            "base_url": "https://api.example.com/v1",
            "api_key": "test-key",
            "model": "test-model",
        },
    )

    assert save_response.status_code == 200

    restarted_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
        )
    )

    status = restarted_client.get("/api/config/llm")
    assert status.status_code == 200
    assert status.json() == {
        "configured": True,
        "base_url": "https://api.example.com/v1",
        "model": "test-model",
    }


def test_api_restores_persisted_content_extraction_provider_after_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "sectorbreaker.sqlite3"
    export_root = tmp_path / "exports"

    first_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
            llm_provider=_default_fake_llm(),
        )
    )

    save_response = first_client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "tavily",
            "tavily_api_key": "tvly-test-key",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "jina",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert save_response.status_code == 200

    restarted_client = TestClient(
        create_app(
            database_path=database_path,
            export_root=export_root,
            llm_provider=_default_fake_llm(),
        )
    )

    status = restarted_client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_extraction_provider"] == "jina"
    assert "jinareader" in status.json()["extraction_providers"]


def test_api_search_test_returns_unconfigured_when_search_missing(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search/test",
        json={"query": "AI agent market"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False


def test_api_updates_search_runtime_config_with_exa_provider(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.post(
        "/api/config/search",
        json={
            "search_provider_mode": "exa",
            "tavily_api_key": "",
            "tavily_endpoint": "https://api.tavily.com/search",
            "serper_api_key": "",
            "serper_endpoint": "https://google.serper.dev/search",
            "brave_api_key": "",
            "brave_endpoint": "https://api.search.brave.com/res/v1/web/search",
            "exa_api_key": "exa-test-key",
            "exa_endpoint": "https://api.exa.ai/search",
            "content_extraction_provider": "http",
            "firecrawl_api_key": "",
            "firecrawl_endpoint": "https://api.firecrawl.dev/v1/scrape",
            "jina_reader_endpoint_prefix": "https://r.jina.ai/http://",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    status = client.get("/api/config/search")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["requested_provider_mode"] == "exa"
    assert "exa" in status.json()["providers"]


def test_api_creates_and_lists_documents(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "AI Reports",
            "domain": "AI 报告",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    created = client.post(
        f"/api/projects/{project_id}/documents",
        json={
            "channel": "assistant_brief",
            "content": "来源：https://www.stats.gov.cn/report\n\n另一来源：https://example.com/blog/best-ai-tools-2026\n\n这是一份调研报告。",
            "file_name": "report.md",
            "mime_type": "text/markdown",
        },
    )

    assert created.status_code == 200
    document_id = created.json()["id"]
    assert created.json()["citation_count"] == 2

    listed = client.get(f"/api/projects/{project_id}/documents")
    fetched = client.get(f"/api/documents/{document_id}")
    segments = client.get(f"/api/documents/{document_id}/segments")
    citations = client.get(f"/api/documents/{document_id}/citations")
    evidence_preview = client.get(f"/api/documents/{document_id}/evidence-preview")
    ingested = client.post(f"/api/documents/{document_id}/ingest-evidence")
    listed_evidence = client.get(f"/api/projects/{project_id}/evidence")

    assert listed.status_code == 200
    assert listed.json()[0]["id"] == document_id
    assert fetched.status_code == 200
    assert fetched.json()["file_name"] == "report.md"
    assert segments.status_code == 200
    assert segments.json()
    assert citations.status_code == 200
    assert citations.json()[0]["source_assessment"]
    assert any(item["source_assessment"]["source_type"] == "government" for item in citations.json())
    assert evidence_preview.status_code == 200
    assert any(item["needs_counterevidence"] is True for item in evidence_preview.json())
    assert any(item["verification_status"] == "verified" for item in evidence_preview.json())
    assert ingested.status_code == 200
    assert ingested.json()["created_count"] == 2
    assert listed_evidence.status_code == 200
    assert len(listed_evidence.json()) == 2

    ingested_again = client.post(f"/api/documents/{document_id}/ingest-evidence")
    assert ingested_again.status_code == 200
    assert ingested_again.json()["created_count"] == 0


def test_api_uploads_text_document_file(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Upload Docs",
            "domain": "上传文档",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/documents/upload",
        data={"channel": "assistant_brief"},
        files={"file": ("brief.md", "# Report\n\n来源：https://example.com/report", "text/markdown")},
    )

    assert response.status_code == 200
    assert response.json()["file_name"] == "brief.md"
    assert response.json()["citation_count"] == 1


def test_api_rejects_unsupported_document_file_type(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Upload Docs",
            "domain": "上传文档",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/documents/upload",
        data={"channel": "assistant_brief"},
        files={"file": ("brief.pptx", b"not supported", "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
    )

    assert response.status_code == 400


def test_api_uploads_docx_document_file(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Upload Word Docs",
            "domain": "上传 Word",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/documents/upload",
        data={"channel": "assistant_brief"},
        files={
            "file": (
                "brief.docx",
                _docx_bytes(["通义千问 DeepSearch 报告", "来源：https://example.com/qwen-report"]),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_name"] == "brief.docx"
    assert "通义千问 DeepSearch 报告" in payload["content"]
    assert payload["citation_count"] == 1


def test_api_pauses_for_supervisor_plan_confirmation(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "编程教育",
            "domain": "编程教育",
            "market_scope": "china",
            "depth": "quick",
            "source_policy": "reliable_first",
        },
    ).json()["id"]

    run = client.post(f"/api/projects/{project_id}/runs").json()
    deadline = time.monotonic() + 5
    result = run
    while time.monotonic() < deadline:
        result = client.get(f"/api/runs/{run['id']}").json()
        if result["status"] == "waiting_for_human":
            break
        time.sleep(0.1)

    assert result["status"] == "waiting_for_human"
    assert result["current_gate"] == "supervisor_plan"

    definition = client.get(f"/api/runs/{run['id']}/workflow-definition")
    assert definition.status_code == 200
    node_ids = {node["id"] for node in definition.json()["nodes"]}
    assert "market_agent" in node_ids


def test_api_exposes_run_snapshot_for_active_run(tmp_path: Path) -> None:
    client = TestClient(create_app(
        database_path=tmp_path / "sectorbreaker.sqlite3",
        export_root=tmp_path / "exports",
        search_provider=FakeSearchProvider(results=[]),
        llm_provider=_default_fake_llm(),
    ))
    project_id = client.post("/api/projects", json={
        "title": "Agent Development",
        "domain": "Agent development",
        "market_scope": "mixed",
        "depth": "quick",
        "source_policy": "open_web",
    }).json()["id"]

    run = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"}).json()
    snapshot = client.get(f"/api/runs/{run['id']}/snapshot")

    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert payload["run_id"] == run["id"]
    assert payload["project_id"] == project_id
    assert payload["status"] in {"collecting", "structuring", "exporting", "completed", "failed"}
    assert "current_stage" in payload
    assert "events" in payload
    assert "artifact_summary" in payload


def test_api_exposes_active_run_for_project_restore(tmp_path: Path) -> None:
    client = TestClient(create_app(
        database_path=tmp_path / "sectorbreaker.sqlite3",
        export_root=tmp_path / "exports",
        search_provider=FakeSearchProvider(results=[]),
        llm_provider=_default_fake_llm(),
    ))
    project_id = client.post("/api/projects", json={
        "title": "Agent Development",
        "domain": "Agent development",
        "market_scope": "mixed",
        "depth": "quick",
        "source_policy": "open_web",
    }).json()["id"]

    run = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"}).json()
    active_run = client.get(f"/api/projects/{project_id}/active-run")

    assert active_run.status_code == 200
    assert active_run.json()["id"] == run["id"]


def test_api_v1_run_creates_knowledge_system_artifacts(tmp_path: Path) -> None:
    search_provider = FakeSearchProvider(results=[{
        "title": "Agent frameworks trend",
        "url": "https://example.com/agent-frameworks",
        "snippet": "Agent frameworks are evolving around tooling, memory, and evaluation.",
    }])
    llm_provider = _default_fake_llm()
    client = TestClient(create_app(
        database_path=tmp_path / "sectorbreaker.sqlite3",
        export_root=tmp_path / "exports",
        search_provider=search_provider,
        llm_provider=llm_provider,
    ))
    project_id = client.post("/api/projects", json={
        "title": "Agent Development",
        "domain": "Agent development",
        "market_scope": "mixed",
        "depth": "quick",
        "source_policy": "open_web",
    }).json()["id"]

    run = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"}).json()
    run_result = _wait_for_run(client, run["id"], timeout=30)
    assert run_result["status"] == "completed"

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    paths = {item["content_path"] for item in artifacts}
    assert "00-领域总览.md" in paths
    assert "01-入门路线.md" in paths
    assert "02-核心概念.md" in paths
    assert "03-玩家与工具地图.md" in paths
    assert "04-趋势与证据.md" in paths
    assert "05-问题与机会.md" in paths
    assert "99-待验证问题.md" in paths
    assert search_provider.search_requests
    assert llm_provider.messages


def test_api_run_auto_includes_ingested_document_evidence(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Document Seed Evidence",
            "domain": "文档证据接入",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    created = client.post(
        f"/api/projects/{project_id}/documents",
        json={
            "channel": "assistant_brief",
            "content": "来源：https://www.stats.gov.cn/report\n\n来源：https://example.com/blog/best-ai-tools-2026",
            "file_name": "report.md",
            "mime_type": "text/markdown",
        },
    )
    document_id = created.json()["id"]
    ingested = client.post(f"/api/documents/{document_id}/ingest-evidence")

    assert ingested.status_code == 200
    assert ingested.json()["created_count"] == 2

    run_response = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    assert run_result["status"] == "completed"

    evidence_response = client.get(f"/api/projects/{project_id}/evidence")
    evidence_ids = {item["id"] for item in evidence_response.json()}

    assert "EV-DOC-" in "".join(evidence_ids)
    assert any(item_id.startswith(f"EV-DOC-{document_id}-") for item_id in evidence_ids)

    artifacts_response = client.get(f"/api/projects/{project_id}/artifacts")
    scope_artifact = next(item for item in artifacts_response.json() if item["id"] == "ART-SCOPE-ANALYSIS")

    assert any(source_id.startswith(f"EV-DOC-{document_id}-") for source_id in scope_artifact["source_evidence_ids"])


def test_api_run_auto_includes_uploaded_assistant_brief_documents(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )
    project_id = client.post(
        "/api/projects",
        json={
            "title": "Assistant Brief Auto Include",
            "domain": "外部报告自动接入",
            "market_scope": "mixed",
            "depth": "quick",
        },
    ).json()["id"]

    upload = client.post(
        f"/api/projects/{project_id}/documents/upload",
        data={"channel": "assistant_brief"},
        files={"file": ("brief.md", "# Report\n\n行业判断A\n\n来源：https://example.com/report", "text/markdown")},
    )

    assert upload.status_code == 200

    run_response = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    assert run_result["status"] == "completed"

    evidence_response = client.get(f"/api/projects/{project_id}/evidence")

    assert any(item["source_type"] == "assistant_brief" for item in evidence_response.json())


def test_api_exposes_source_registry_status(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.get("/api/config/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["packs"]
    pack_names = {pack["name"] for pack in payload["packs"]}
    assert {"company_china_pack", "tech_frontier_pack"}.issubset(pack_names)
    connectors = {
        connector["key"]: connector
        for pack in payload["packs"]
        for connector in pack["connectors"]
    }
    assert connectors["qcc_openapi"]["connector_type"] == "commercial_api"
    assert connectors["qcc_openapi"]["configured"] is False
    assert connectors["gsxt_manual"]["requires_manual_review"] is True
    assert connectors["github_api"]["required_env_keys"] == ["GITHUB_TOKEN"]
