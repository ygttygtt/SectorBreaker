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

    def fake_http_json(method: str, path: str, payload=None):
        calls.append((method, path, payload))
        if path == "/api/config/llm":
            return {"configured": True, "base_url": "https://api.example.com", "model": "test-model"}
        if path == "/api/config/search":
            return {"configured": True, "providers": ["tavily"]}
        if path == "/api/config/search/test":
            return {"success": True, "result_count": 2, "providers": ["tavily"]}
        if path == "/api/projects":
            return {"id": "proj-1", "source_policy": "open_web"}
        if path == "/api/projects/proj-1/runs?auto_run=true":
            return {"id": "run-1", "status": "running"}
        if path == "/api/runs/run-1":
            return {"id": "run-1", "status": "completed"}
        if path == "/api/projects/proj-1/evidence":
            return [
                {"id": "EV-1", "source_type": "web", "source_channel": "search", "source_title": "Official source"},
                {"id": "EV-2", "source_type": "assistant_brief", "source_channel": "assistant_brief", "source_title": "Brief"},
            ]
        if path == "/api/projects/proj-1/artifacts":
            return [
                {"id": "A1", "content_path": "00-领域总览.md"},
                {"id": "A2", "content_path": "01-入门路线.md"},
                {"id": "A3", "content_path": "02-核心概念.md"},
                {"id": "A4", "content_path": "03-玩家与工具地图.md"},
                {"id": "A5", "content_path": "04-趋势与证据.md"},
                {"id": "A6", "content_path": "05-问题与机会.md"},
                {"id": "A7", "content_path": "99-待验证问题.md"},
            ]
        if path == "/api/projects/proj-1/exports":
            return {
                "project_id": "proj-1",
                "artifact_paths": [
                    "00-领域总览.md",
                    "01-入门路线.md",
                    "02-核心概念.md",
                    "03-玩家与工具地图.md",
                    "04-趋势与证据.md",
                    "05-问题与机会.md",
                    "99-待验证问题.md",
                    "_sources/evidence-ledger.md",
                    "manifest.json",
                ],
                "evidence_ids": ["EV-1"],
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
            return {"success": True, "result_count": 1}
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
