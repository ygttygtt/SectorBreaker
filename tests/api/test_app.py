from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.providers.fakes import FakeLLMProvider, FakeSearchProvider


def test_api_runs_research_and_exports_markdown(tmp_path: Path) -> None:
    client = TestClient(
        create_app(database_path=tmp_path / "sectorbreaker.sqlite3", export_root=tmp_path / "exports")
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

    run_response = client.post(f"/api/projects/{project_id}/runs")
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "completed"

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
        create_app(database_path=tmp_path / "sectorbreaker.sqlite3", export_root=tmp_path / "exports")
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

    client.post(f"/api/projects/{project_id}/runs")

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

    run_response = client.post(f"/api/projects/{project_id}/runs")
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "completed"

    evidence_response = client.get(f"/api/projects/{project_id}/evidence")
    assert evidence_response.json()[1]["source_title"] == "宠物服务市场"
