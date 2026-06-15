# Frontend

Vite + React + TypeScript workbench for SectorBreaker.

The frontend is a research cockpit. It should display project state, graph progress, evidence, artifacts, human review prompts, project Q&A, and export actions.

The frontend must not own research workflow decisions. It calls FastAPI contracts documented in `../docs/05-api-contract.md`.
