import asyncio
import importlib.util
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from backend.app.providers.interfaces import ExtractedPage, SearchResult, SourceAssessment


def _load_smoke_module():
    module_path = Path(__file__).resolve().parents[2] / "run_search_smoke_test.py"
    spec = importlib.util.spec_from_file_location("run_search_smoke_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_smoke_script_exits_with_error_when_search_not_configured(monkeypatch) -> None:
    module = _load_smoke_module()
    monkeypatch.setattr(module, "load_local_env", lambda: None)
    monkeypatch.setattr(module, "build_search_provider", lambda: None)
    monkeypatch.setattr(module, "build_content_extraction_provider", lambda: object())

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        result = asyncio.run(module.main())

    assert result == 1
    assert "No search provider configured" in stderr.getvalue()


def test_smoke_script_prints_json_and_summary(monkeypatch) -> None:
    module = _load_smoke_module()
    captured_query = {}

    class StubSearchProvider:
        async def search(self, query):
            captured_query["query"] = query
            return [
                SearchResult(
                    title="Official Market Report",
                    url="https://example.org/report",
                    snippet="Official statistics.",
                )
            ]

    class StubExtractionProvider:
        async def extract_url(self, url: str):
            return ExtractedPage(
                url=url,
                raw_text="Official market report body content.",
                title="Official Market Report",
                domain="example.org",
                extraction_provider="http",
            )

    class StubSourceVerifier:
        async def assess_source(self, **kwargs):
            return SourceAssessment(
                source_type="government",
                source_quality="high",
                is_original_source=True,
                is_marketing_like=False,
                recommended_verification_status="verified",
                reliability_notes="Looks authoritative.",
            )

    monkeypatch.setattr(module, "load_local_env", lambda: None)
    monkeypatch.setattr(module, "build_search_provider", lambda: StubSearchProvider())
    monkeypatch.setattr(module, "build_content_extraction_provider", lambda: StubExtractionProvider())
    monkeypatch.setattr(module, "HeuristicSourceVerificationProvider", lambda: StubSourceVerifier())
    monkeypatch.setenv("SECTORBREAKER_SMOKE_SOURCE_POLICY", "reliable_only")
    monkeypatch.setenv("SECTORBREAKER_SMOKE_ALLOWED_DOMAINS", "sec.gov,investor.example.com")
    monkeypatch.setenv("SECTORBREAKER_SMOKE_BLOCKED_DOMAINS", "medium.com")

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        result = asyncio.run(module.main())

    output = stdout.getvalue()
    assert result == 0
    assert captured_query["query"].allowed_domains == ["sec.gov", "investor.example.com"]
    assert "medium.com" in captured_query["query"].blocked_domains
    assert "substack.com" in captured_query["query"].blocked_domains
    assert "\"result_count\": 1" in output
    assert "\"source_policy\": \"reliable_only\"" in output
    assert "source_policy: reliable_only" in output
    assert "allowed_domains: ['sec.gov', 'investor.example.com']" in output
    assert "blocked_domains:" in output
    assert "medium.com" in output
    assert "substack.com" in output
    assert "search_provider: StubSearchProvider" in output
    assert "first_result_source_quality: high" in output
