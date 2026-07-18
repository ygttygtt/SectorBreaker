"""Check that production code cannot drift back to archived workflow paths.

This is a lightweight architectural guard for the SectorBreaker Agent Kernel
cutover. It intentionally scans source text rather than importing modules so it
can catch forbidden references before runtime.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_ROOTS = [
    ROOT / "backend" / "app",
    ROOT / "frontend" / "src",
]

LEGACY_SMOKE_ALARM_FILE = ROOT / "backend" / "app" / "api" / "app.py"

RETIRED_PRODUCTION_PATHS = [
    ROOT / "backend" / "app" / "graph" / "workflow.py",
    ROOT / "backend" / "app" / "graph" / "planner.py",
    ROOT / "backend" / "app" / "providers" / "job_sources.py",
    ROOT / "backend" / "app" / "talent_demand" / "__init__.py",
    ROOT / "backend" / "app" / "talent_demand" / "pipeline.py",
    ROOT / "backend" / "app" / "talent_demand" / "models.py",
    ROOT / "backend" / "app" / "talent_demand" / "export.py",
    ROOT / "backend" / "app" / "talent_demand" / "extraction.py",
    ROOT / "backend" / "app" / "talent_demand" / "skills.py",
    ROOT / "backend" / "app" / "talent_demand" / "source_coverage.py",
]

FORBIDDEN_IMPORT_MARKERS = [
    "backend.app.v1_pipeline",
    "backend.app.v2_pipeline",
    "backend.app.legacy",
    "v2_react_graph",
    "legacy_v1_pipeline",
    "legacy_fixed_v2_pipeline",
    "run_v1_knowledge_pipeline",
    "run_v2_react_knowledge_pipeline",
    "backend.app.graph.workflow",
    "backend.app.graph.planner",
    "run_research_workflow",
    "run_workflow_until_pause",
    "backend.app.talent_demand",
    "backend.app.providers.job_sources",
    "run_talent_demand_pipeline",
    "JobSourceProvider",
    "build_job_source_provider",
]

FORBIDDEN_RUNTIME_MARKERS = [
    "Knowledge Builder",
    "Document Writer",
    "specialist_react_loop",
    "EV-V1-",
    "ART-V1-",
    "已使用保底",
    "talent_demand",
    "TalentScope",
    "talent-v1",
    "boss_job",
    "/api/config/job-source",
]

LEGACY_SMOKE_ALARM_MARKERS = {
    "Knowledge Builder",
    "Document Writer",
    "specialist_react_loop",
    "EV-V1-",
    "ART-V1-",
    "已使用保底",
}


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for root in PRODUCTION_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() in {".py", ".ts", ".tsx"}:
                files.append(path)
    return sorted(files)


def main() -> int:
    violations: list[str] = []
    for path in RETIRED_PRODUCTION_PATHS:
        if path.exists():
            violations.append(f"{path.relative_to(ROOT)}: retired production path still exists")

    for path in iter_source_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        for marker in FORBIDDEN_IMPORT_MARKERS:
            if marker in text:
                violations.append(f"{relative}: forbidden import/path marker {marker!r}")
        for marker in FORBIDDEN_RUNTIME_MARKERS:
            if marker not in text:
                continue
            if path == LEGACY_SMOKE_ALARM_FILE and marker in LEGACY_SMOKE_ALARM_MARKERS:
                continue
            violations.append(f"{relative}: forbidden runtime marker {marker!r}")

    if violations:
        print("Version isolation check failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("Version isolation check passed: retired workflows and enterprise paths are unreachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
