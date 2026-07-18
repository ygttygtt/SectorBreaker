import importlib.util
import inspect
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.schemas import ProjectMode
from tools.check_version_isolation import main as check_version_isolation


def test_retired_backend_modules_and_injection_hook_are_absent() -> None:
    retired_modules = (
        "backend.app.graph.workflow",
        "backend.app.graph.planner",
        "backend.app.providers.job_sources",
        "backend.app.talent_demand.pipeline",
        "backend.app.talent_demand.models",
    )

    assert all(importlib.util.find_spec(module_name) is None for module_name in retired_modules)
    assert "job_source_provider" not in inspect.signature(create_app).parameters
    assert list(ProjectMode) == [ProjectMode.DOMAIN_KNOWLEDGE]


def test_retired_enterprise_api_and_project_mode_are_unreachable(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
        )
    )

    assert client.get("/api/config/job-source").status_code == 404
    assert client.post("/api/config/job-source", json={"enabled": True}).status_code == 404

    response = client.post(
        "/api/projects",
        json={
            "title": "Retired enterprise request",
            "domain": "knowledge management",
            "market_scope": "china",
            "depth": "quick",
            "project_mode": "talent_demand",
        },
    )

    assert response.status_code == 422
    assert client.get("/api/projects").json() == []


def test_version_isolation_scan_covers_retired_paths() -> None:
    assert check_version_isolation() == 0
