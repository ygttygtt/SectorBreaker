# Runnable V1 Rearchitecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a genuinely runnable V1 path from topic input to real API-backed Obsidian knowledge export.

**Architecture:** Add a stable backend `RunSnapshot` contract and a simplified V1 pipeline facade that reuses existing providers, repository, evidence, artifact, and exporter code. Rebuild the frontend around backend-owned run state instead of local-only phases. Prove the product with both fake-provider regression tests and a real-provider acceptance script.

**Tech Stack:** FastAPI, Pydantic, SQLite, existing provider interfaces, Vite, React, TypeScript, Vitest, pytest.

---

## File Structure

- Modify `backend/app/schemas/runs.py`: add V1 run stage, progress, snapshot, and artifact summary schemas.
- Modify `backend/app/storage/sqlite.py`: add active-run and event helpers needed by snapshots.
- Create `backend/app/v1_pipeline.py`: simplified runnable V1 pipeline facade.
- Modify `backend/app/api/app.py`: expose snapshot endpoints and route V1 runs through the facade.
- Modify `backend/app/exporters/markdown.py`: stabilize V1 Obsidian file layout.
- Modify `tests/api/test_app.py`: add backend V1 regression tests.
- Modify `run_real_search_acceptance.py`: make real API acceptance verify LLM, Tavily, run completion, evidence, artifacts, export files.
- Modify `frontend/src/api/client.ts`: add snapshot and knowledge-system API types.
- Modify `frontend/src/App.tsx`: simplify to project start, run console, result view driven by backend snapshots.
- Modify `frontend/src/App.test.tsx`: add snapshot restore, failure display, and result rendering tests.

## Task 1: Backend Run Snapshot Contract

**Files:**
- Modify: `backend/app/schemas/runs.py`
- Modify: `backend/app/storage/sqlite.py`
- Modify: `backend/app/api/app.py`
- Test: `tests/api/test_app.py`

- [ ] **Step 1: Write failing API snapshot test**

Add a test that creates a project, starts an auto run with fake providers, calls `GET /api/runs/{run_id}/snapshot`, and expects:

```python
def test_api_exposes_run_snapshot_for_active_run(tmp_path: Path) -> None:
    client = TestClient(create_app(
        database_path=tmp_path / "sectorbreaker.sqlite3",
        export_root=tmp_path / "exports",
        search_provider=FakeSearchProvider(results=[]),
        llm_provider=_default_fake_llm(),
    ))
    project_id = client.post("/api/projects", json={
        "title": "Agent Development",
        "domain": "Agent development",
        "market_scope": "mixed",
        "depth": "quick",
        "source_policy": "open_web",
    }).json()["id"]

    run = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"}).json()
    snapshot = client.get(f"/api/runs/{run['id']}/snapshot")

    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert payload["run_id"] == run["id"]
    assert payload["project_id"] == project_id
    assert payload["status"] in {"collecting", "structuring", "exporting", "completed", "failed"}
    assert "current_stage" in payload
    assert "events" in payload
    assert "artifact_summary" in payload
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest --basetemp .tmp_pytest tests/api/test_app.py::test_api_exposes_run_snapshot_for_active_run -q
```

Expected: FAIL with `404` or missing endpoint/schema.

- [ ] **Step 3: Add schemas**

In `backend/app/schemas/runs.py`, add:

```python
class V1RunStage(StrEnum):
    IDLE = "idle"
    COLLECTING = "collecting"
    STRUCTURING = "structuring"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"


class RunProgress(BaseModel):
    current: int = 0
    total: int = 0


class RunArtifactSummary(BaseModel):
    id: str
    title: str
    content_path: str
    artifact_type: str


class RunSnapshot(BaseModel):
    run_id: str
    project_id: str
    status: V1RunStage
    current_stage: str
    progress: RunProgress = Field(default_factory=RunProgress)
    events: list[RunEvent] = Field(default_factory=list)
    errors: list[RunEvent] = Field(default_factory=list)
    artifact_summary: list[RunArtifactSummary] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

- [ ] **Step 4: Add repository helpers**

In `SQLiteRepository`, add:

```python
def get_run(self, run_id: str) -> ResearchRun:
    ...

def get_active_run(self, project_id: str) -> ResearchRun | None:
    ...

def list_run_events(self, run_id: str) -> list[RunEvent]:
    ...
```

Use existing row conversion helpers if present; otherwise mirror existing run/event serialization.

- [ ] **Step 5: Add snapshot endpoint**

In `backend/app/api/app.py`, add:

```python
@app.get("/api/runs/{run_id}/snapshot")
def get_run_snapshot(run_id: str):
    run = repository.get_run(run_id)
    events = repository.list_run_events(run_id)
    artifacts = repository.list_artifacts(run.project_id)
    return build_run_snapshot(run, events, artifacts).model_dump(mode="json")
```

Implement `build_run_snapshot` near API helpers. Map existing `RunStatus` plus `current_gate` to V1 stages.

- [ ] **Step 6: Run test to verify GREEN**

Run the same pytest command. Expected: PASS.

## Task 2: V1 Pipeline Facade And Knowledge Artifacts

**Files:**
- Create: `backend/app/v1_pipeline.py`
- Modify: `backend/app/api/app.py`
- Modify: `backend/app/schemas/artifacts.py`
- Test: `tests/api/test_app.py`

- [ ] **Step 1: Write failing V1 loop test**

Add:

```python
def test_api_v1_run_creates_knowledge_system_artifacts(tmp_path: Path) -> None:
    search_provider = FakeSearchProvider(results=[{
        "title": "Agent frameworks trend",
        "url": "https://example.com/agent-frameworks",
        "snippet": "Agent frameworks are evolving around tooling, memory, and evaluation.",
    }])
    client = TestClient(create_app(
        database_path=tmp_path / "sectorbreaker.sqlite3",
        export_root=tmp_path / "exports",
        search_provider=search_provider,
        llm_provider=_default_fake_llm(),
    ))
    project_id = client.post("/api/projects", json={
        "title": "Agent Development",
        "domain": "Agent development",
        "market_scope": "mixed",
        "depth": "quick",
        "source_policy": "open_web",
    }).json()["id"]
    run = client.post(f"/api/projects/{project_id}/runs", params={"auto_run": "true"}).json()
    run_result = _wait_for_run(client, run["id"], timeout=30)
    assert run_result["status"] == "completed"

    artifacts = client.get(f"/api/projects/{project_id}/artifacts").json()
    paths = {item["content_path"] for item in artifacts}
    assert "00-领域总览.md" in paths
    assert "01-入门路线.md" in paths
    assert "02-核心概念.md" in paths
    assert "03-玩家与工具地图.md" in paths
    assert "04-趋势与证据.md" in paths
    assert "05-问题与机会.md" in paths
    assert "99-待验证问题.md" in paths
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest --basetemp .tmp_pytest tests/api/test_app.py::test_api_v1_run_creates_knowledge_system_artifacts -q
```

Expected: FAIL because current artifact paths are old workflow paths.

- [ ] **Step 3: Add artifact types if needed**

In `ArtifactType`, add:

```python
DOMAIN_OVERVIEW = "domain_overview"
LEARNING_PATH = "learning_path"
CORE_CONCEPTS = "core_concepts"
PLAYER_TOOL_MAP = "player_tool_map"
TREND_EVIDENCE = "trend_evidence"
PROBLEM_OPPORTUNITY_MAP = "problem_opportunity_map"
UNRESOLVED_QUESTIONS = "unresolved_questions"
```

- [ ] **Step 4: Create `backend/app/v1_pipeline.py`**

Expose:

```python
async def run_v1_knowledge_pipeline(
    *,
    project: ResearchProject,
    repository: SQLiteRepository,
    search_provider: SearchProvider | None,
    content_extraction_provider: ContentExtractionProvider,
    llm_provider: LLMProvider | None,
    emit: Callable[[RunEvent], Awaitable[None]] | None = None,
) -> list[Artifact]:
    ...
```

The pipeline must:

- emit collecting/structuring/exporting-friendly events;
- call Tavily/search provider when policy allows and provider exists;
- store search results as evidence through existing `EvidenceItem`;
- call the real LLM provider for structured knowledge content when configured;
- produce the seven V1 artifacts listed in the test;
- store artifacts with `repository.add_artifact`.

- [ ] **Step 5: Route auto runs through V1 pipeline**

In `backend/app/api/app.py`, change the background run path so `auto_run=true` uses `run_v1_knowledge_pipeline` for the simplified V1 result.

Keep old workflow functions available for compatibility but do not make the frontend depend on plan confirmation for V1.

- [ ] **Step 6: Run test to verify GREEN**

Run the same pytest command. Expected: PASS.

## Task 3: Stable Obsidian Export Layout

**Files:**
- Modify: `backend/app/exporters/markdown.py`
- Test: `tests/unit/test_markdown_exporter.py`
- Test: `tests/api/test_app.py`

- [ ] **Step 1: Write failing exporter test**

Add a test that creates the seven V1 artifacts, calls `MarkdownExporter.export_project`, and asserts:

```python
assert set(manifest.artifact_paths) >= {
    "00-领域总览.md",
    "01-入门路线.md",
    "02-核心概念.md",
    "03-玩家与工具地图.md",
    "04-趋势与证据.md",
    "05-问题与机会.md",
    "99-待验证问题.md",
    "_sources/evidence-ledger.md",
    "manifest.json",
}
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest --basetemp .tmp_pytest tests/unit/test_markdown_exporter.py -q
```

Expected: FAIL because evidence path is currently `证据库.md` and manifest may not be included in `artifact_paths`.

- [ ] **Step 3: Update exporter**

Write evidence ledger to `_sources/evidence-ledger.md`. Include `manifest.json` in manifest artifact paths. Keep backward compatibility for arbitrary artifact paths.

- [ ] **Step 4: Run exporter tests**

Run the same pytest command. Expected: PASS.

## Task 4: Frontend Snapshot-Driven V1 UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing frontend tests**

Add tests for:

- app restores an active run by calling `/api/projects/{id}/active-run` or `/api/runs/{id}/snapshot`;
- failed snapshot renders visible error text;
- completed snapshot renders artifacts and export action.

- [ ] **Step 2: Run frontend tests to verify RED**

Run:

```bash
cd frontend
npm test
```

Expected: FAIL due missing snapshot client/UI.

- [ ] **Step 3: Add client methods**

Add TypeScript interfaces for `RunSnapshot`, `RunProgress`, and `RunArtifactSummary`, plus:

```ts
getRunSnapshot(runId: string): Promise<RunSnapshot>
getActiveRun(projectId: string): Promise<RunResponse | null>
```

- [ ] **Step 4: Rework App state**

Use three durable UI phases:

- `start`
- `running`
- `result`

Render run console from `RunSnapshot`, not local-only event phase.

When SSE disconnects, poll snapshot.

- [ ] **Step 5: Simplify settings surface**

Keep advanced provider fields available, but visually emphasize Tavily and LLM as the primary path.

- [ ] **Step 6: Run frontend tests and build**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected: both PASS.

## Task 5: Real API Acceptance Path

**Files:**
- Modify: `run_real_search_acceptance.py`
- Create or modify: `docs/16-runnable-v1-acceptance.md`
- Test: `tests/unit/test_real_search_acceptance_script.py`

- [ ] **Step 1: Write failing script test**

Update the unit test to assert the script checks:

- `/api/config/llm`;
- `/api/config/search`;
- `/api/config/search/test`;
- project creation;
- real run completion;
- evidence count;
- artifact count;
- export manifest includes V1 files.

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest --basetemp .tmp_pytest tests/unit/test_real_search_acceptance_script.py -q
```

Expected: FAIL until script checks all required conditions.

- [ ] **Step 3: Update acceptance script**

Make `run_real_search_acceptance.py` fail unless:

- LLM config is present;
- search config is present;
- search test returns at least one result;
- run completes;
- project evidence includes search-channel evidence;
- project artifacts include the seven V1 files;
- export manifest includes `_sources/evidence-ledger.md`.

- [ ] **Step 4: Add operator doc**

Create `docs/16-runnable-v1-acceptance.md` with the exact command order:

```bash
python run_real_search_acceptance.py
```

Document the expected output keys and what to do when LLM or Tavily config is missing.

- [ ] **Step 5: Run unit test**

Run the same pytest command. Expected: PASS.

## Final Verification

- [ ] Run focused backend tests:

```bash
python -m pytest --basetemp .tmp_pytest tests/api/test_app.py tests/unit/test_markdown_exporter.py tests/unit/test_real_search_acceptance_script.py -q
```

- [ ] Run frontend tests:

```bash
cd frontend
npm test
npm run build
```

- [ ] Start backend and frontend:

```bash
python -m uvicorn backend.app.api.app:app --host 127.0.0.1 --port 8030
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

- [ ] Run real acceptance:

```bash
$env:SECTORBREAKER_API_BASE_URL="http://127.0.0.1:8030"
python run_real_search_acceptance.py
```

Expected: real Tavily and real LLM run completes and exports the V1 Obsidian vault.

