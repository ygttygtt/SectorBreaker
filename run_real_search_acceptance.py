"""End-to-end acceptance check for the real search stack."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from backend.app.env import load_local_env


def _api_base_url() -> str:
    return os.getenv("SECTORBREAKER_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _http_json(method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    url = f"{_api_base_url()}{path}"
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to call {url}: {exc}") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc

    return json.loads(raw)


def _poll_run(run_id: str, timeout_seconds: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        run = _http_json("GET", f"/api/runs/{run_id}")
        status = run.get("status")
        if status in {"completed", "failed", "waiting_for_human"}:
            return run
        time.sleep(0.5)
    raise RuntimeError(f"Run {run_id} did not finish within {timeout_seconds} seconds.")


def _print_section(title: str) -> None:
    print(f"\n== {title} ==")


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_backend_start_hint() -> None:
    print(
        "Backend does not appear to be running. Start it first, for example:\n"
        "  uvicorn backend.app.api.app:app --host 127.0.0.1 --port 8000 --reload",
        file=sys.stderr,
    )


def main() -> int:
    load_local_env()

    source_policy = os.getenv("SECTORBREAKER_ACCEPTANCE_SOURCE_POLICY", "open_web")
    query = os.getenv("SECTORBREAKER_ACCEPTANCE_QUERY", "AI agent market map")
    project_title = os.getenv("SECTORBREAKER_ACCEPTANCE_PROJECT_TITLE", "Search Acceptance Check")
    project_domain = os.getenv("SECTORBREAKER_ACCEPTANCE_PROJECT_DOMAIN", "搜索验收")
    market_scope = os.getenv("SECTORBREAKER_ACCEPTANCE_MARKET_SCOPE", "mixed")
    depth = os.getenv("SECTORBREAKER_ACCEPTANCE_DEPTH", "quick")
    max_results = int(os.getenv("SECTORBREAKER_ACCEPTANCE_MAX_RESULTS", "3"))
    run_timeout_seconds = float(os.getenv("SECTORBREAKER_ACCEPTANCE_RUN_TIMEOUT_SECONDS", "60"))

    allowed_domains = [
        item.strip()
        for item in os.getenv("SECTORBREAKER_ACCEPTANCE_ALLOWED_DOMAINS", "").split(",")
        if item.strip()
    ]
    blocked_domains = [
        item.strip()
        for item in os.getenv("SECTORBREAKER_ACCEPTANCE_BLOCKED_DOMAINS", "").split(",")
        if item.strip()
    ]

    _print_section("Search Config")
    try:
        config_status = _http_json("GET", "/api/config/search")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        _print_backend_start_hint()
        return 1
    _print_json(config_status)
    if not config_status.get("configured"):
        print("Search is not configured. Fill .env or save provider keys in the UI first.", file=sys.stderr)
        return 1

    _print_section("Search Test")
    search_test = _http_json(
        "POST",
        "/api/config/search/test",
        {
            "query": query,
            "market_scope": market_scope,
            "source_policy": source_policy,
            "max_results": max_results,
            "allowed_domains": allowed_domains,
            "blocked_domains": blocked_domains,
        },
    )
    _print_json(search_test)
    if not search_test.get("success"):
        print("Search connectivity test failed.", file=sys.stderr)
        return 1
    if int(search_test.get("result_count", 0)) <= 0:
        print("Search connectivity test returned no results.", file=sys.stderr)
        return 1

    _print_section("Project Creation")
    project = _http_json(
        "POST",
        "/api/projects",
        {
            "title": project_title,
            "domain": project_domain,
            "market_scope": market_scope,
            "depth": depth,
            "source_policy": source_policy,
        },
    )
    _print_json(project)
    project_id = str(project["id"])

    _print_section("Run Trigger")
    run = _http_json(
        "POST",
        f"/api/projects/{project_id}/runs?{urllib.parse.urlencode({'auto_run': 'true'})}",
    )
    _print_json(run)
    run_id = str(run["id"])

    _print_section("Run Poll")
    run_result = _poll_run(run_id, timeout_seconds=run_timeout_seconds)
    _print_json(run_result)
    if run_result.get("status") != "completed":
        print(f"Run did not complete successfully: {run_result.get('status')}", file=sys.stderr)
        return 1

    _print_section("Evidence Check")
    evidence = _http_json("GET", f"/api/projects/{project_id}/evidence")
    assert isinstance(evidence, list)
    search_channel_evidence = [
        item
        for item in evidence
        if isinstance(item, dict) and item.get("source_channel") == "search"
    ]
    _print_json(
        {
            "project_id": project_id,
            "evidence_count": len(evidence),
            "search_channel_evidence_count": len(search_channel_evidence),
            "sample_evidence_ids": [item.get("id") for item in evidence[:5] if isinstance(item, dict)],
            "sample_search_evidence_ids": [
                item.get("id")
                for item in search_channel_evidence[:5]
                if isinstance(item, dict)
            ],
        }
    )

    if not search_channel_evidence:
        print("No search-channel evidence was written into the project evidence ledger.", file=sys.stderr)
        return 1

    print("\nAcceptance passed: search config, live search test, project run, and evidence writeback all succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
