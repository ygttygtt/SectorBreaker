"""Run the full workflow with real LLM for '大健康保健品' domain."""

import asyncio
import json
import os
import time
from pathlib import Path

# Configure LLM
os.environ["LLM_BASE_URL"] = "https://token-plan-cn.xiaomimimo.com/v1"
os.environ["LLM_API_KEY"] = "tp-cmpxaysx0yb6tyhap8y3wdkwnnpprwmnux8cr6ohoxz6rx0o"
os.environ["LLM_MODEL"] = "mimo-v2.5-pro"

from backend.app.graph.workflow import run_workflow_until_pause
from backend.app.providers.factory import build_llm_provider
from backend.app.schemas import ResearchProject, MarketScope, ResearchDepth, RunEvent

OUTPUT_DIR = Path("test-output")
OUTPUT_DIR.mkdir(exist_ok=True)


async def main():
    llm = build_llm_provider()
    if llm is None:
        print("ERROR: LLM provider not configured")
        return

    print(f"LLM: {llm.base_url} / {llm.model}")
    print(f"Domain: 大健康保健品")
    print("=" * 60)

    project = ResearchProject(
        id="test-health",
        title="大健康保健品",
        domain="大健康保健品",
        market_scope=MarketScope.CHINA,
        depth=ResearchDepth.STANDARD,
    )

    events_log = []

    async def emit(event: RunEvent):
        ts = time.strftime("%H:%M:%S")
        msg = f"[{ts}] {event.event_type} | {event.gate} | {event.message}"
        print(msg)
        events_log.append({
            "timestamp": ts,
            "event_type": event.event_type,
            "gate": event.gate,
            "step": event.step,
            "agent": event.agent,
            "message": event.message,
        })

    print("\n--- Running workflow (auto_run=True) ---\n")

    state, paused, completed = await run_workflow_until_pause(
        project,
        llm_provider=llm,
        emitter=emit,
        auto_run=True,
    )

    print(f"\n{'=' * 60}")
    print(f"Completed: {completed}, Paused gate: {paused}")
    print(f"Current gate: {state.get('current_gate')}")
    print(f"Artifacts: {len(state.get('artifacts', []))}")
    print(f"Evidence: {len(state.get('evidence', []))}")
    print(f"QA issues: {state.get('qa_issues', [])}")

    # Save events log
    with open(OUTPUT_DIR / "events.json", "w", encoding="utf-8") as f:
        json.dump(events_log, f, ensure_ascii=False, indent=2)
    print(f"\nEvents saved to {OUTPUT_DIR / 'events.json'}")

    # Save each artifact
    artifacts_dir = OUTPUT_DIR / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    for art in state.get("artifacts", []):
        filename = art.get("id", "unknown").lower().replace("-", "_") + ".md"
        filepath = artifacts_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(art.get("content", ""))
        print(f"  Artifact: {filepath.name} ({len(art.get('content', ''))} chars)")

    # Save evidence
    with open(OUTPUT_DIR / "evidence.json", "w", encoding="utf-8") as f:
        json.dump(state.get("evidence", []), f, ensure_ascii=False, indent=2)
    print(f"Evidence saved to {OUTPUT_DIR / 'evidence.json'}")

    # Save full state
    with open(OUTPUT_DIR / "state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, default=str)
    print(f"Full state saved to {OUTPUT_DIR / 'state.json'}")

    print(f"\n{'=' * 60}")
    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
