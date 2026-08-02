"""Run the live-only demo gate without printing credentials.

The API performs real LLM, search, extraction, A2A Task/Artifact, SQLite and
export probes. This CLI is the single operator-facing gate used before an
interview; it exits non-zero whenever a critical check fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from backend.app.schemas import DemoReadiness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SectorBreaker Demo Readiness gate")
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="running SectorBreaker API base URL (default: %(default)s)",
    )
    parser.add_argument("--timeout", type=int, default=120, help="whole readiness request timeout")
    parser.add_argument("--json", action="store_true", help="print the sanitized JSON result")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    endpoint = args.api_base_url.rstrip("/") + "/api/demo/readiness"
    started = datetime.now(UTC)
    try:
        request = Request(endpoint, headers={"Accept": "application/json"})
        with urlopen(request, timeout=max(10, args.timeout)) as response:  # noqa: S310 - operator supplied local API
            payload = json.loads(response.read().decode("utf-8"))
        readiness = DemoReadiness.model_validate(payload)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValidationError) as exc:
        print(f"DEMO BLOCKED: readiness API failed ({type(exc).__name__})", file=sys.stderr)
        print("Fix: start the API, verify the configured port, then rerun this command.", file=sys.stderr)
        return 2

    if args.json:
        print(readiness.model_dump_json(indent=2))
    else:
        print("SectorBreaker Demo Preflight")
        print(f"Checked at: {readiness.checked_at.isoformat()}")
        print(f"Elapsed: {(datetime.now(UTC) - started).total_seconds():.1f}s")
        for check in readiness.checks:
            mark = "PASS" if check.ready else "FAIL"
            critical = "critical" if check.critical else "warning"
            print(f"[{mark}] {check.label} ({critical}) — {check.detail}")
            if not check.ready and check.action:
                print(f"       Fix: {check.action}")
        print("DEMO READY" if readiness.ready else "DEMO BLOCKED")
    return 0 if readiness.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
