"""Execute the ten-domain, real-provider Demo Ready release gate.

This script intentionally refuses to run unless `/api/demo/readiness` is
green. It never injects fake providers or substitute content.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DOMAINS = [
    "量子传感",
    "合成生物学",
    "固态电池",
    "隐私计算",
    "空间计算",
    "农业机器人",
    "小型模块化核反应堆",
    "数字疗法",
    "卫星互联网",
    "可持续航空燃料",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SectorBreaker ten-domain live release gate")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--deadline", type=int, default=300)
    parser.add_argument("--report", type=Path, help="optional JSON report path")
    return parser.parse_args()


class Api:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, payload: dict | None = None, timeout: int = 120):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator supplied local API
            return json.loads(response.read().decode("utf-8"))


def run_domain(api: Api, domain: str, deadline: int) -> dict:
    started = time.monotonic()
    project = api.call("POST", "/api/projects", {
        "title": f"Demo Gate · {domain}",
        "domain": domain,
        "market_scope": "mixed",
        "depth": "quick",
        "source_policy": "reliable_first",
        "project_mode": "domain_knowledge",
    })
    run = api.call("POST", f"/api/projects/{project['id']}/challenge-runs", {
        "domain": domain,
        "deadline_seconds": deadline,
        "output_type": "starter_note",
        "orchestration_mode": "adaptive_multi_agent",
        "source_policy": "reliable_first",
        "publish_policy": "propose_before_publish",
    })
    while True:
        current = api.call("GET", f"/api/runs/{run['id']}")
        if current["status"] in {"waiting_for_human", "completed", "failed", "interrupted"}:
            break
        if time.monotonic() - started > deadline + 20:
            raise TimeoutError(f"{domain} exceeded release deadline")
        time.sleep(2)
    mission = api.call("GET", f"/api/runs/{run['id']}/agent-mission")
    elapsed = time.monotonic() - started
    research = [item for item in mission["work_orders"] if item["task_type"] == "research"]
    editor = next((item for item in mission["deliverables"] if item.get("draft_markdown")), None)
    claim_checks = [check for item in mission["deliverables"] for check in item["claim_checks"]]
    evidence = api.call("GET", f"/api/projects/{project['id']}/evidence")
    source_urls = {item.get("source_url") for item in evidence if item.get("source_url")}
    assertions = {
        "within_deadline": elapsed <= deadline,
        "waiting_for_review": mission["status"] == "waiting_for_review",
        "two_research_orders": len(research) >= 2,
        "all_tasks_accepted": all(item["status"] == "accepted" for item in mission["work_orders"]),
        "two_real_sources": len(source_urls) >= 2,
        "claim_checked": bool(claim_checks),
        "starter_note_length": bool(editor and 1500 <= len(editor["draft_markdown"]) <= 3600),
        "project_evidence_only": bool(editor and set(editor["evidence_ids"]) <= {item["id"] for item in evidence}),
    }
    if not all(assertions.values()):
        raise RuntimeError(f"acceptance failed: {json.dumps(assertions, ensure_ascii=False)}")
    change_set_id = mission["change_set_id"]
    api.call("POST", f"/api/projects/{project['id']}/change-sets/{change_set_id}/approve")
    applied = api.call("POST", f"/api/projects/{project['id']}/change-sets/{change_set_id}/apply")
    exported = api.call("POST", f"/api/projects/{project['id']}/exports")
    rolled_back = api.call("POST", f"/api/projects/{project['id']}/change-sets/{change_set_id}/rollback")
    reexported = api.call("POST", f"/api/projects/{project['id']}/exports")
    assertions.update({
        "apply": applied["status"] == "applied",
        "export": bool(exported.get("artifact_paths")),
        "rollback": rolled_back["status"] == "rolled_back",
        "reexport_after_rollback": bool(reexported.get("artifact_paths")),
    })
    return {
        "domain": domain,
        "project_id": project["id"],
        "run_id": run["id"],
        "elapsed_seconds": round(elapsed, 2),
        "source_count": len(source_urls),
        "claim_check_count": len(claim_checks),
        "assertions": assertions,
        "passed": all(assertions.values()),
    }


def main() -> int:
    args = parse_args()
    api = Api(args.api_base_url)
    try:
        readiness = api.call("GET", "/api/demo/readiness", timeout=130)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"DEMO BLOCKED: preflight unavailable ({type(exc).__name__})", file=sys.stderr)
        return 2
    if not readiness.get("ready"):
        failed = [item["label"] for item in readiness.get("checks", []) if item.get("critical") and not item.get("ready")]
        print("DEMO BLOCKED: " + ", ".join(failed), file=sys.stderr)
        return 2

    report = {"started_at": datetime.now(UTC).isoformat(), "live_only": True, "results": []}
    for index, domain in enumerate(DOMAINS, 1):
        print(f"[{index}/10] {domain} ...", flush=True)
        try:
            result = run_domain(api, domain, args.deadline)
        except Exception as exc:  # continue to produce failure distribution
            result = {"domain": domain, "passed": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
        report["results"].append(result)
        print("PASS" if result["passed"] else f"FAIL — {result.get('error', result.get('assertions'))}", flush=True)
    report["completed_at"] = datetime.now(UTC).isoformat()
    report["passed"] = all(item["passed"] for item in report["results"])
    report["passed_count"] = sum(1 for item in report["results"] if item["passed"])
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "passed_count": report["passed_count"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
