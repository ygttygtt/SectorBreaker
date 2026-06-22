"""Run the full workflow + export for '大健康保健品' domain."""

import asyncio
import json
import os
import time
from pathlib import Path

os.environ.setdefault("LLM_BASE_URL", "")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("LLM_MODEL", "")

from backend.app.exporters.markdown import MarkdownExporter
from backend.app.graph.workflow import run_workflow_until_pause
from backend.app.providers.factory import build_llm_provider
from backend.app.schemas import ResearchProject, MarketScope, ResearchDepth, RunEvent

OUTPUT_DIR = Path("test-output")


async def main():
    llm = build_llm_provider()
    print(f"LLM: {llm.base_url} / {llm.model}\n")

    project = ResearchProject(
        id="test-health", title="大健康保健品", domain="大健康保健品",
        market_scope=MarketScope.CHINA, depth=ResearchDepth.STANDARD,
    )

    events_log = []

    async def emit(event: RunEvent):
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {event.event_type} | {event.gate} | {event.message[:60]}")
        events_log.append({
            "timestamp": ts, "event_type": event.event_type,
            "gate": event.gate, "message": event.message,
        })

    print("=" * 60)
    print("Running workflow (auto_run=True)...")
    print("=" * 60)

    state, paused, completed = await run_workflow_until_pause(
        project, llm_provider=llm, emitter=emit, auto_run=True,
    )

    print(f"\n{'=' * 60}")
    print(f"Completed: {completed} | Artifacts: {len(state.get('artifacts', []))} | Evidence: {len(state.get('evidence', []))}")

    # Convert to schema objects
    from backend.app.schemas import Artifact, EvidenceItem, ArtifactType, VerificationStatus
    artifacts = []
    for a in state.get("artifacts", []):
        try:
            artifacts.append(Artifact(**a))
        except Exception:
            pass

    evidence = []
    for e in state.get("evidence", []):
        try:
            evidence.append(EvidenceItem(**e))
        except Exception:
            pass

    # Export
    print("\nExporting...")
    exporter = MarkdownExporter(OUTPUT_DIR)
    manifest = exporter.export_project(project, artifacts, evidence)

    # List output
    print(f"\nExported to: {OUTPUT_DIR / project.title}")
    print(f"Files: {len(manifest.artifact_paths)}")

    export_dir = OUTPUT_DIR / project.title
    for root, dirs, files in os.walk(export_dir):
        level = root.replace(str(export_dir), "").count(os.sep)
        indent = "  " * level
        print(f"{indent}{os.path.basename(root)}/")
        for f in files:
            size = os.path.getsize(os.path.join(root, f))
            print(f"{indent}  {f} ({size} bytes)")

    # Save events
    with open(OUTPUT_DIR / "events.json", "w", encoding="utf-8") as f:
        json.dump(events_log, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
