"""Tests for GET /api/runs/{run_id}/trace export endpoint."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.app import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(
        database_path=tmp_path / "sb.sqlite3",
        export_root=tmp_path / "exports",
    ))


def test_trace_export_returns_all_run_events(tmp_path: Path) -> None:
    client = _client(tmp_path)
    project = client.post("/api/projects", json={
        "title": "T",
        "domain": "d",
        "market_scope": "mixed",
        "depth": "quick",
    }).json()
    run = client.post(f"/api/projects/{project['id']}/runs").json()

    resp = client.get(f"/api/runs/{run['id']}/trace")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run["id"]
    assert body["project_id"] == project["id"]
    assert "events" in body
    assert isinstance(body["events"], list)


def test_trace_export_404_for_unknown_run(tmp_path: Path) -> None:
    client = _client(tmp_path)

    resp = client.get("/api/runs/nonexistent/trace")

    assert resp.status_code == 404
