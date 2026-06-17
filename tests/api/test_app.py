import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.providers.fakes import FakeLLMProvider, FakeSearchProvider


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

    list_response = client.get("/api/projects")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == project_id

    detail_response = client.get(f"/api/projects/{project_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["domain"] == "AI Agent 工具"


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


def test_api_run_uses_injected_search_and_llm_providers(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            search_provider=FakeSearchProvider(
                results=[
                    {
                        "title": "宠物服务市场",
                        "url": "https://example.com/pet-services",
                        "snippet": "宠物服务需求增长。",
                    }
                ]
            ),
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
    assert "supervisor_plan" in node_ids
    assert "evidence_ledger" in node_ids


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
