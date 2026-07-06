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

ALLOWED_FILES = {
    ROOT / "backend" / "app" / "api" / "app.py",  # fail-closed legacy marker smoke alarm
    ROOT / "backend" / "app" / "agent_state" / "models.py",  # cognitive layer labels, not workflow
    ROOT / "backend" / "app" / "agents" / "specialists.py",  # specialist contracts/prompts, not product entrypoint
}

FORBIDDEN_IMPORT_MARKERS = [
    "backend.app.v1_pipeline",
    "backend.app.v2_pipeline",
    "backend.app.legacy",
    "v2_react_graph",
    "legacy_v1_pipeline",
    "legacy_fixed_v2_pipeline",
    "run_v1_knowledge_pipeline",
    "run_v2_react_knowledge_pipeline",
]

FORBIDDEN_RUNTIME_MARKERS = [
    "Knowledge Builder",
    "Document Writer",
    "specialist_react_loop",
    "EV-V1-",
    "ART-V1-",
    "已使用保底",
]


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
    for path in iter_source_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        for marker in FORBIDDEN_IMPORT_MARKERS:
            if marker in text:
                violations.append(f"{relative}: forbidden import/path marker {marker!r}")
        if path not in ALLOWED_FILES:
            for marker in FORBIDDEN_RUNTIME_MARKERS:
                if marker in text:
                    violations.append(f"{relative}: forbidden runtime marker {marker!r}")

    if violations:
        print("Version isolation check failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("Version isolation check passed: production paths do not reference legacy workflows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

