import importlib.util
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


def _load_acceptance_module():
    module_path = Path(__file__).resolve().parents[2] / "run_real_search_acceptance.py"
    spec = importlib.util.spec_from_file_location("run_real_search_acceptance", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_acceptance_script_fails_when_search_not_configured(monkeypatch) -> None:
    module = _load_acceptance_module()
    monkeypatch.setattr(module, "load_local_env", lambda: None)
    monkeypatch.setattr(
        module,
        "_http_json",
        lambda method, path, payload=None: (
            {"configured": True}
            if path == "/api/config/llm"
            else {"configured": False}
            if path == "/api/config/search"
            else {}
        ),
    )

    stderr = io.StringIO()
    stdout = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = module.main()

    assert result == 1
    assert "Search is not configured" in stderr.getvalue()
    assert "Search Config" in stdout.getvalue()


def test_acceptance_script_prints_backend_start_hint_when_api_unreachable(monkeypatch) -> None:
    module = _load_acceptance_module()
    monkeypatch.setattr(module, "load_local_env", lambda: None)
    monkeypatch.setattr(module, "_http_json", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Failed to call http://127.0.0.1:8000/api/config/search: [WinError 10061]")))

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        result = module.main()

    assert result == 1
    assert "Backend does not appear to be running" in stderr.getvalue()
    assert "uvicorn backend.app.api.app:app" in stderr.getvalue()


def test_acceptance_script_runs_full_happy_path(monkeypatch) -> None:
    module = _load_acceptance_module()
    monkeypatch.setattr(module, "load_local_env", lambda: None)
    calls: list[tuple[str, str, dict | None]] = []
    run_polls = 0

    def fake_http_json(method: str, path: str, payload=None):
        nonlocal run_polls
        calls.append((method, path, payload))
        if path == "/api/config/llm":
            return {"configured": True, "base_url": "https://api.example.com", "model": "test-model"}
        if path == "/api/config/search":
            return {"configured": True, "providers": ["tavily"]}
        if path == "/api/config/search/test":
            return {
                "success": True,
                "result_count": 2,
                "providers": ["tavily"],
                "extracted_page": {"raw_text_preview": "readable extracted content " * 8},
            }
        if path == "/api/projects":
            return {"id": "proj-1", "source_policy": "open_web"}
        if path == "/api/projects/proj-1/runs?auto_run=true":
            return {"id": "run-1", "status": "running"}
        if path == "/api/runs/run-1":
            run_polls += 1
            return {"id": "run-1", "status": "waiting_for_human" if run_polls == 1 else "completed"}
        if path == "/api/projects/proj-1/change-sets":
            return [{"id": "CS-1", "status": "proposed", "origin_run_id": "run-1"}]
        if path == "/api/projects/proj-1/change-sets/CS-1/approve":
            return {"id": "CS-1", "status": "approved"}
        if path == "/api/projects/proj-1/change-sets/CS-1/apply":
            return {"id": "CS-1", "status": "applied"}
        if path == "/api/runs/run-1/resume":
            return {"run_id": "run-1", "status": "resumed"}
        if path == "/api/projects/proj-1/evidence":
            return [
                {
                    "id": "EV-1",
                    "source_type": "web",
                    "source_channel": "search",
                    "source_title": "Official source",
                    "extraction_provider": "http_content",
                    "raw_excerpt": "production extracted evidence body " * 8,
                    "verification_status": "partially_verified",
                },
                {"id": "EV-2", "source_type": "assistant_brief", "source_channel": "assistant_brief", "source_title": "Brief"},
            ]
        if path == "/api/projects/proj-1/artifacts":
            return [
                {
                    "id": "A1",
                    "active": True,
                    "content_path": "docs/domain-overview.md",
                    "schema_version": "v3-knowledge-ops",
                    "source_evidence_ids": ["EV-1"],
                    "content": "# Domain overview\n\n## Evidence\n\n" + "Substantial cited knowledge. " * 30,
                },
            ]
        if path == "/api/projects/proj-1/exports":
            return {
                "project_id": "proj-1",
                "artifact_paths": [
                    "docs/domain-overview.md",
                    ".sectorbreaker/project.json",
                    ".sectorbreaker/agent_state.json",
                    ".sectorbreaker/evidence_ledger.json",
                    ".sectorbreaker/artifact_manifest.json",
                    ".sectorbreaker/health_snapshot.json",
                    ".sectorbreaker/maintenance_backlog.json",
                    ".sectorbreaker/change_sets.json",
                    ".sectorbreaker/open_questions.json",
                    ".sectorbreaker/trace_summary.json",
                    "manifest.json",
                ],
                "evidence_ids": ["EV-1"],
                "active_artifacts": [{"id": "A1", "path": "docs/domain-overview.md"}],
            }
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    monkeypatch.setenv("SECTORBREAKER_ACCEPTANCE_ALLOWED_DOMAINS", "sec.gov,stats.gov.cn")
    monkeypatch.setenv("SECTORBREAKER_ACCEPTANCE_BLOCKED_DOMAINS", "medium.com")

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        result = module.main()

    output = stdout.getvalue()
    assert result == 0
    assert "Acceptance passed" in output
    assert any(item[1] == "/api/config/llm" for item in calls)
    assert any(item[1] == "/api/projects/proj-1/artifacts" for item in calls)
    assert any(item[1] == "/api/projects/proj-1/exports" for item in calls)
    assert any(item[1] == "/api/runs/run-1/resume" for item in calls)
    search_test_call = next(item for item in calls if item[1] == "/api/config/search/test")
    assert search_test_call[2]["allowed_domains"] == ["sec.gov", "stats.gov.cn"]
    assert search_test_call[2]["blocked_domains"] == ["medium.com"]


def test_acceptance_script_fails_when_llm_not_configured(monkeypatch) -> None:
    module = _load_acceptance_module()
    monkeypatch.setattr(module, "load_local_env", lambda: None)
    monkeypatch.setattr(
        module,
        "_http_json",
        lambda method, path, payload=None: {"configured": False} if path == "/api/config/llm" else {},
    )

    stderr = io.StringIO()
    stdout = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = module.main()

    assert result == 1
    assert "LLM is not configured" in stderr.getvalue()
    assert "LLM Config" in stdout.getvalue()


def test_acceptance_script_fails_when_no_open_web_evidence_written(monkeypatch) -> None:
    module = _load_acceptance_module()
    monkeypatch.setattr(module, "load_local_env", lambda: None)

    def fake_http_json(method: str, path: str, payload=None):
        if path == "/api/config/llm":
            return {"configured": True}
        if path == "/api/config/search":
            return {"configured": True}
        if path == "/api/config/search/test":
            return {
                "success": True,
                "result_count": 1,
                "extracted_page": {"raw_text_preview": "readable extracted content " * 8},
            }
        if path == "/api/projects":
            return {"id": "proj-1"}
        if path == "/api/projects/proj-1/runs?auto_run=true":
            return {"id": "run-1", "status": "running"}
        if path == "/api/runs/run-1":
            return {"id": "run-1", "status": "completed"}
        if path == "/api/projects/proj-1/evidence":
            return [
                {"id": "EV-brief", "source_type": "assistant_brief", "source_channel": "assistant_brief"},
                {"id": "EV-user", "source_type": "user_material", "source_channel": "user_upload"},
                {"id": "EV-system", "source_type": "official", "source_channel": "system"},
            ]
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(module, "_http_json", fake_http_json)

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        result = module.main()

    assert result == 1
    assert "No search-channel evidence" in stderr.getvalue()
