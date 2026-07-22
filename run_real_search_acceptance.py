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


def _complete_run_with_reviews(
    *,
    project_id: str,
    run_id: str,
    timeout_seconds: float,
    max_reviews: int = 3,
) -> dict[str, object]:
    for review_index in range(max_reviews + 1):
        result = _poll_run(run_id, timeout_seconds=timeout_seconds)
        if result.get("status") != "waiting_for_human":
            return result
        if review_index >= max_reviews:
            return result

        change_sets = _http_json("GET", f"/api/projects/{project_id}/change-sets")
        assert isinstance(change_sets, list)
        proposed = next(
            (
                item for item in change_sets
                if isinstance(item, dict)
                and item.get("status") == "proposed"
                and item.get("origin_run_id") in {None, run_id}
            ),
            None,
        )
        if proposed is None:
            return result
        change_set_id = str(proposed["id"])
        _http_json("POST", f"/api/projects/{project_id}/change-sets/{change_set_id}/approve")
        applied = _http_json("POST", f"/api/projects/{project_id}/change-sets/{change_set_id}/apply")
        if applied.get("status") != "applied":
            raise RuntimeError(f"ChangeSet {change_set_id} did not apply: {applied}")
        _http_json(
            "POST",
            f"/api/runs/{run_id}/resume",
            {
                "guidance": "验收已审查并应用当前 ChangeSet，请检查本轮目标并完成运行。",
                "plan_confirmed": True,
            },
        )
    raise AssertionError("unreachable")


def _print_section(title: str) -> None:
    print(f"\n== {title} ==")


def _print_json(payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(rendered.encode(encoding, errors="replace").decode(encoding))


def _print_backend_start_hint() -> None:
    print(
        "Backend does not appear to be running. Start it first, for example:\n"
        "  uvicorn backend.app.api.app:app --host 127.0.0.1 --port 8000 --reload",
        file=sys.stderr,
    )


V3_REQUIRED_STATE_PATHS = {
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
}

FORBIDDEN_MARKERS = {
    "EV-V1-",
    "ART-V1-",
    "Knowledge Builder",
    "Document Writer",
    "specialist_react_loop",
    "已使用保底",
}


def main() -> int:
    load_local_env()

    source_policy = os.getenv("SECTORBREAKER_ACCEPTANCE_SOURCE_POLICY", "open_web")
    query = os.getenv("SECTORBREAKER_ACCEPTANCE_QUERY", "AI agent market map")
    project_title = os.getenv("SECTORBREAKER_ACCEPTANCE_PROJECT_TITLE", "Search Acceptance Check")
    project_domain = os.getenv("SECTORBREAKER_ACCEPTANCE_PROJECT_DOMAIN", "搜索验收")
    market_scope = os.getenv("SECTORBREAKER_ACCEPTANCE_MARKET_SCOPE", "mixed")
    depth = os.getenv("SECTORBREAKER_ACCEPTANCE_DEPTH", "quick")
    max_results = int(os.getenv("SECTORBREAKER_ACCEPTANCE_MAX_RESULTS", "3"))
    run_timeout_seconds = float(os.getenv("SECTORBREAKER_ACCEPTANCE_RUN_TIMEOUT_SECONDS", "600"))

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

    _print_section("LLM Config")
    try:
        llm_status = _http_json("GET", "/api/config/llm")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        _print_backend_start_hint()
        return 1
    _print_json(llm_status)
    if not llm_status.get("configured"):
        print("LLM is not configured. Fill .env or save an OpenAI-compatible LLM config in the UI first.", file=sys.stderr)
        return 1

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
    extracted_preview = (search_test.get("extracted_page") or {}).get("raw_text_preview", "")
    if len(str(extracted_preview).strip()) < 80:
        print("Search self-test did not return readable extracted page content.", file=sys.stderr)
        return 1

    existing_project_id = os.getenv("SECTORBREAKER_ACCEPTANCE_PROJECT_ID", "").strip()
    if existing_project_id:
        project_id = existing_project_id
        _print_section("Existing Project Recheck")
        _print_json({"project_id": project_id})
    else:
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
        run_result = _complete_run_with_reviews(
            project_id=project_id,
            run_id=run_id,
            timeout_seconds=run_timeout_seconds,
        )
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
    extracted_evidence = [
        item for item in search_channel_evidence
        if item.get("extraction_provider") and len(str(item.get("raw_excerpt") or "").strip()) >= 80
    ]
    if not extracted_evidence:
        print("No production Agent evidence contains readable extracted body and provenance.", file=sys.stderr)
        return 1
    if any(item.get("verification_status") == "verified" for item in search_channel_evidence):
        print("Heuristic search evidence was incorrectly promoted to verified.", file=sys.stderr)
        return 1

    _print_section("Artifact Check")
    artifacts = _http_json("GET", f"/api/projects/{project_id}/artifacts")
    assert isinstance(artifacts, list)
    active_artifacts = [
        item for item in artifacts
        if isinstance(item, dict) and item.get("active", True)
    ]
    invalid_artifacts = [
        item.get("id") for item in active_artifacts
        if not str(item.get("schema_version") or "").startswith("v3-")
        or len(str(item.get("content") or "").strip()) < 400
        or not item.get("source_evidence_ids")
        or any(marker in str(item.get("content") or "") for marker in FORBIDDEN_MARKERS)
    ]
    artifact_paths = {item.get("content_path") for item in active_artifacts if item.get("content_path")}
    _print_json(
        {
            "project_id": project_id,
            "active_artifact_count": len(active_artifacts),
            "invalid_v3_artifact_ids": invalid_artifacts,
            "artifact_paths": sorted(artifact_paths),
        }
    )
    if not active_artifacts or invalid_artifacts:
        print(f"V3 active artifacts are missing or invalid: {invalid_artifacts}", file=sys.stderr)
        return 1

    _print_section("Export Check")
    export_manifest = _http_json("POST", f"/api/projects/{project_id}/exports")
    _print_json(export_manifest)
    export_paths = set(export_manifest.get("artifact_paths", []))
    missing_export_paths = sorted(V3_REQUIRED_STATE_PATHS - export_paths)
    if missing_export_paths:
        print(f"V3 export manifest is missing control-plane paths: {missing_export_paths}", file=sys.stderr)
        return 1
    active_artifact_ids = {str(item.get("id")) for item in active_artifacts}
    exported_artifact_ids = {
        str(item.get("id"))
        for item in export_manifest.get("active_artifacts", [])
        if isinstance(item, dict)
    }
    if not active_artifact_ids.issubset(exported_artifact_ids):
        print("V3 export manifest does not contain every active artifact id.", file=sys.stderr)
        return 1

    print("\nAcceptance passed: live search/extraction, production Agent evidence, V3 active artifacts, and Obsidian control-plane export all succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
