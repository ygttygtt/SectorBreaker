# V1.3 Talent Demand Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a B-side talent-demand intelligence mode while preserving the existing V1/V1.2 domain-knowledge-base workflow.

**Architecture:** Keep the current V1.2 learning-oriented domain knowledge pipeline as the default stable path. Add a new `talent_demand` mode beside it, backed by shared provider interfaces, document ingestion, Evidence Ledger, Source Coverage Matrix, and Obsidian export. Talent-demand mode starts from user-uploaded JD/report materials, adds search-provider evidence as supplement, optionally aligns skills with external occupation/skill taxonomies, then writes a dedicated talent-demand knowledge vault.

**Tech Stack:** FastAPI, Pydantic, SQLite, existing `SearchProvider` / document ingestion / EvidenceItem schemas, React/Vite frontend, Markdown/Obsidian exporter, focused pytest/vitest checks.

---

## Product Positioning

### Scenario

`Talent Demand Intelligence Agent` serves HR, training companies, education products, recruiting platforms, and business leaders who need evidence-based insight into a role or skill market.

Typical user question:

> For `大模型应用开发工程师`, what do companies actually require, which skills appear most often, how do junior/mid/senior requirements differ, what salary/experience signals exist, and what learning/project path should a training team or talent team build?

### Why This Is Not A Personal Job-Search Tool

- The target user is not an individual applying for jobs.
- The output is a market/skill-demand intelligence base for hiring, training, curriculum design, or workforce planning.
- The product emphasizes source coverage, evidence quality, sample limitations, skill normalization, and reusable knowledge artifacts.

### Non-Negotiable Compatibility Rule

Every V1.3 change must preserve the old V1.2 flow:

- Existing landing default can still run a normal domain-knowledge-base project.
- Existing V1.2 artifacts, evidence ledger, export layout, progress events, and result page still work.
- New talent-demand mode must be additive: new mode flag, new pipeline branch, new artifact templates, new source coverage panel. Do not mutate the old V1 path into a talent-specific path.
- Focused regression tests must prove old V1 behavior still works after each milestone.

---

## Source Strategy

### Mature Projects / Services To Reuse Or Reference

- JobSpy: open-source job-posting collection library covering LinkedIn, Indeed, Glassdoor, Google, ZipRecruiter and more. Treat as an optional local adapter with legal/ToS caution, not a default dependency.
- Adzuna API: job-search API suitable for a legal API-backed job-posting source.
- O*NET Web Services: official occupation, skills, knowledge, and abilities baseline for U.S. occupations.
- ESCO API: EU occupation and skills taxonomy, useful for skill normalization and occupation mapping.
- Lightcast Open Skills: skill taxonomy reference; useful conceptually even if first implementation does not call it.
- Firecrawl / Jina / HTTP extraction: use existing extraction provider boundary for public pages discovered by search, instead of writing custom scrapers per site.

### Legal / Operational Guardrails

- Do not implement login-gated scraping.
- Do not bypass anti-bot protections.
- Do not directly scrape BOSS 直聘、猎聘、智联、前程无忧, LinkedIn, Indeed, or similar sites as the default path.
- Prefer user-uploaded JD text, user-provided reports, official APIs, public search results, company career pages discovered through search, and documented data APIs.
- Mark scraped/search-derived snippets as partial evidence unless page extraction and source assessment succeed.
- Always show sample-size and source-coverage limitations in the output.

---

## Target User Flow

1. User selects project mode:
   - `领域建库` keeps the current V1.2 flow.
   - `人才需求情报` enables talent-demand inputs and output templates.
2. User fills:
   - target role, e.g. `大模型应用开发工程师`;
   - market/region, e.g. `中国一线城市`, `全国`, `global`;
   - target purpose: `招聘画像`, `课程设计`, `能力模型`, `求职市场分析`, `企业培训`;
   - optional industry scope;
   - optional uploaded materials: JD collection, Kimi/Gemini/DeepSeek report, internal role description, course outline.
3. System ingests uploaded materials first.
4. If materials are thin, system runs search-provider queries as supplement.
5. System extracts structured role-demand facts:
   - role title;
   - company/industry when available;
   - location;
   - salary/range when available;
   - experience requirement;
   - education requirement;
   - skills/tools/frameworks;
   - responsibilities;
   - seniority indicators;
   - evidence ids and source type.
6. System normalizes skills and groups them into a demand matrix.
7. System generates a talent-demand Obsidian vault.
8. Result page shows Source Coverage Matrix and export readiness.

---

## Data Model Additions

### New Lightweight Mode Field

Prefer a small additive field on project creation/runtime state:

```python
project_mode: Literal["domain_knowledge", "talent_demand"] = "domain_knowledge"
```

If changing `ResearchProject` schema is too invasive for the first pass, store mode in run config or project metadata and keep API backward compatible.

### Pydantic Models

Create a focused module, for example `backend/app/talent_demand/models.py`.

```python
class TalentDemandInput(BaseModel):
    target_role: str
    market_scope: str = "mixed"
    region: str | None = None
    industry_scope: str | None = None
    purpose: Literal["hiring_profile", "curriculum_design", "capability_model", "market_research", "training"] = "market_research"
    user_notes: str = ""


class JobPostingSignal(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    salary_text: str | None = None
    experience_text: str | None = None
    education_text: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    seniority: Literal["junior", "mid", "senior", "lead", "unknown"] = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class SkillDemandItem(BaseModel):
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    category: Literal["programming", "ai_model", "framework", "data", "backend", "product", "soft_skill", "domain", "other"] = "other"
    frequency: int = 0
    seniority_distribution: dict[str, int] = Field(default_factory=dict)
    representative_evidence_ids: list[str] = Field(default_factory=list)


class SourceCoverageMatrix(BaseModel):
    total_evidence: int = 0
    uploaded_jd_count: int = 0
    uploaded_report_count: int = 0
    search_result_count: int = 0
    extracted_page_count: int = 0
    occupation_standard_count: int = 0
    salary_signal_count: int = 0
    experience_signal_count: int = 0
    skill_signal_count: int = 0
    weak_or_unverified_count: int = 0
    gaps: list[str] = Field(default_factory=list)


class TalentDemandKnowledgeBase(BaseModel):
    overview: str = ""
    postings: list[JobPostingSignal] = Field(default_factory=list)
    skill_matrix: list[SkillDemandItem] = Field(default_factory=list)
    role_levels: list[str] = Field(default_factory=list)
    company_industry_patterns: list[str] = Field(default_factory=list)
    salary_experience_notes: list[str] = Field(default_factory=list)
    learning_path: list[str] = Field(default_factory=list)
    portfolio_requirements: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    source_coverage: SourceCoverageMatrix = Field(default_factory=SourceCoverageMatrix)
```

---

## Pipeline Design

Create `backend/app/talent_demand/pipeline.py` rather than overloading `backend/app/v1_pipeline.py`.

### Stages

1. `talent_source_intake`
   - Read existing project documents.
   - Treat uploaded JD/report text as first-class input.
   - Use search provider only as supplement.

2. `jd_signal_extraction`
   - Use deterministic regex for obvious fields where possible.
   - Use LLM structured extraction for responsibilities, skills, seniority and ambiguous fields.
   - Keep evidence ids attached.

3. `skill_normalization`
   - Normalize aliases using simple rules plus LLM grouping.
   - Optionally enrich with O*NET/ESCO adapter results when configured.

4. `source_coverage`
   - Build Source Coverage Matrix.
   - Emit warning when JD sample count is low, salary fields are missing, region is unclear, or sources are mostly search snippets.

5. `talent_synthesis`
   - Build `TalentDemandKnowledgeBase`.
   - Keep LLM as analyzer/writer, not as unsupported fact generator.

6. `artifact_review`
   - Reuse bounded V1.2 artifact review style.
   - Review should expand missing details and mark gaps, not shorten content.

7. `obsidian_export`
   - Export talent-specific main docs and cards.

### Progress Events

Emit user-visible events:

- `Talent Source Scout`: collecting JD/report/search materials.
- `JD Extractor`: extracting role, company, salary, experience, responsibilities and skills.
- `Skill Normalizer`: grouping aliases and building skill matrix.
- `Source Coverage`: checking sample coverage and gaps.
- `Talent Analyst`: generating role demand knowledge base.
- `Artifact Reviewer`: checking depth and evidence.
- `Export Writer`: writing talent-demand Obsidian vault.

---

## Export Layout

Talent-demand mode should export a different vault layout without affecting V1.2:

```text
README.md
00-岗位需求总览.md
01-岗位画像与分层.md
02-技能需求矩阵.md
03-公司与行业分布.md
04-薪资与经验要求.md
05-学习路径与能力模型.md
06-作品集与项目要求.md
99-待验证问题.md
skills/
roles/
companies/
_sources/evidence-ledger.md
manifest.json
```

### Main Artifacts

- `00-岗位需求总览.md`: what the role market looks like, with sample limitations.
- `01-岗位画像与分层.md`: junior/mid/senior/lead patterns.
- `02-技能需求矩阵.md`: skill frequency, aliases, categories, evidence.
- `03-公司与行业分布.md`: company/industry patterns when available.
- `04-薪资与经验要求.md`: only if supported by evidence; otherwise mark as insufficient.
- `05-学习路径与能力模型.md`: capability model for hiring/training/curriculum.
- `06-作品集与项目要求.md`: project evidence expected by employers.
- `99-待验证问题.md`: missing sample coverage, region bias, unclear salary/skill signals.

### Cards

- `skills/<skill>.md`: definition, aliases, why demanded, representative evidence.
- `roles/<role-level>.md`: level expectations and evidence.
- `companies/<company>.md`: only generated when company info is present and useful.

---

## Frontend Design

### Keep Old Flow

Landing page should default to the current domain-knowledge mode.

### Add Mode Switch

Add a clear but non-disruptive mode selector:

- `领域建库`
- `人才需求情报`

When `人才需求情报` is selected, show:

- target role;
- region;
- industry scope;
- target purpose;
- upload JD/report area;
- hint: “优先使用你上传的 JD/报告，搜索只作为补充。”

### Result Page Additions

For talent-demand runs, show:

- JD 样本数;
- 搜索来源数;
- 用户上传材料数;
- 外部报告数;
- 技能信号数;
- 薪资信号数;
- 经验信号数;
- 待验证问题数.

This should reuse the current quality-summary panel style where possible.

### Workbench Visual Polish

Without a large redesign, make the UI feel more like a workbench:

- Rename high-level panels to “任务配置 / 运行轨迹 / 信源覆盖 / 产物工作台”.
- Add mode-specific badges.
- Use source-coverage cards instead of raw counts only.
- Keep current graph and log stream, but make active stage text clearer for talent-demand events.

---

## Implementation Tasks

### Task 1: Project Mode Contract

**Files:**

- Modify: `backend/app/schemas/projects.py`
- Modify: `backend/app/api/app.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `docs/05-api-contract.md`
- Test: focused API/project schema tests.

**Steps:**

- [ ] Add additive project/run mode support with default `domain_knowledge`.
- [ ] Ensure existing project creation payloads still work without `project_mode`.
- [ ] Update frontend API type.
- [ ] Add a regression test that old create-project payload creates a normal V1 project.
- [ ] Add a test that `project_mode="talent_demand"` is accepted.

### Task 2: Talent Demand Models

**Files:**

- Create: `backend/app/talent_demand/__init__.py`
- Create: `backend/app/talent_demand/models.py`
- Test: `tests/unit/test_talent_demand_models.py`

**Steps:**

- [ ] Add Pydantic models listed in this plan.
- [ ] Add validation tests for empty/default source coverage.
- [ ] Add serialization tests so models can be stored as JSON and embedded in artifact generation.

### Task 3: JD / Report Signal Extraction

**Files:**

- Create: `backend/app/talent_demand/extraction.py`
- Test: `tests/unit/test_talent_demand_extraction.py`

**Steps:**

- [ ] Implement deterministic helpers for salary, experience, education, and common skill tokens.
- [ ] Implement `extract_job_posting_signals_from_text(text, evidence_id)` returning one or more `JobPostingSignal`.
- [ ] Keep extraction conservative: missing fields remain `None` or empty lists.
- [ ] Add fixture tests using short Chinese JD samples.
- [ ] Add tests proving extraction attaches evidence ids.

### Task 4: Skill Normalization

**Files:**

- Create: `backend/app/talent_demand/skills.py`
- Test: `tests/unit/test_talent_demand_skills.py`

**Steps:**

- [ ] Add alias grouping rules for common AI/LLM terms: `LLM`, `大模型`, `RAG`, `Agent`, `LangChain`, `LangGraph`, `Python`, `FastAPI`, `向量数据库`.
- [ ] Implement `build_skill_matrix(postings)` returning `SkillDemandItem`.
- [ ] Add tests for alias merging and frequency counting.
- [ ] Keep future taxonomy enrichment behind a function boundary; do not call external taxonomy APIs in default tests.

### Task 5: Source Coverage Matrix

**Files:**

- Create: `backend/app/talent_demand/source_coverage.py`
- Test: `tests/unit/test_talent_demand_source_coverage.py`

**Steps:**

- [ ] Count source channels from `EvidenceItem`: search, assistant brief, user upload, system/standard.
- [ ] Count postings with salary, experience and skills.
- [ ] Add gap messages for low sample count, no salary signal, no experience signal, or search-only evidence.
- [ ] Add tests for mixed uploaded/search evidence.

### Task 6: Talent Demand Pipeline

**Files:**

- Create: `backend/app/talent_demand/pipeline.py`
- Modify: `backend/app/api/app.py`
- Test: `tests/unit/test_talent_demand_pipeline.py`

**Steps:**

- [ ] Implement `run_talent_demand_pipeline(...)`.
- [ ] Read repository documents for the project and convert uploaded JD/report materials into seed evidence.
- [ ] Use existing search provider to supplement if user materials are thin.
- [ ] Build postings, skill matrix, source coverage and knowledge base.
- [ ] Generate artifacts using deterministic fallback when LLM is not configured.
- [ ] Emit progress events for every stage.
- [ ] In `app.py`, route `project_mode="talent_demand"` to this pipeline while leaving default V1 unchanged.
- [ ] Add tests proving default V1 still routes to `run_v1_knowledge_pipeline`.
- [ ] Add tests proving talent mode produces talent artifacts without a real LLM/search provider.

### Task 7: Talent Demand Export

**Files:**

- Create or modify: `backend/app/talent_demand/export.py`
- Modify: `backend/app/exporters/markdown.py` only if shared README detection is needed.
- Test: `tests/unit/test_talent_demand_export.py`

**Steps:**

- [ ] Render the talent-demand main document layout.
- [ ] Render `skills/`, `roles/`, and optional `companies/` cards.
- [ ] Ensure front matter includes `type`, `status`, `evidence_ids`, `tags`, `project_mode`.
- [ ] Ensure exported README explains sample limitations and source coverage.
- [ ] Add tests checking file paths and README content.

### Task 8: Frontend Mode Selector

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

**Steps:**

- [ ] Add mode selector while keeping `领域建库` as default.
- [ ] Show talent-demand fields only when selected.
- [ ] Send `project_mode` and talent fields to backend.
- [ ] Keep current `开始构建知识库` flow working unchanged for old mode.
- [ ] Add tests for default old mode and talent-demand project creation payload.

### Task 9: Source Hub Settings Upgrade

**Files:**

- Modify: `frontend/src/components/ConfigPanel.tsx`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/App.test.tsx` or `frontend/src/components/ConfigPanel` tests if split exists.

**Steps:**

- [ ] Surface existing backend providers: Tavily, Serper, Brave, Exa.
- [ ] Keep Tavily as recommended default.
- [ ] Show provider mode: `auto`, `tavily`, `serper`, `brave`, `exa`, `multi`.
- [ ] Keep missing-key warnings provider-specific.
- [ ] Add a “do not scrape login-gated job boards” hint in talent-demand mode.
- [ ] Add tests ensuring old Tavily-only config path still works.

### Task 10: Frontend Source Coverage Panel

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

**Steps:**

- [ ] Display Source Coverage Matrix when talent-demand artifact data contains it.
- [ ] Fall back to existing quality summary when matrix is absent.
- [ ] Show gaps prominently but as warnings, not fatal errors.
- [ ] Add tests for matrix display and old V1 summary display.

### Task 11: Workbench Visual Polish

**Files:**

- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.tsx` only for labels and small layout changes.

**Steps:**

- [ ] Improve landing/workbench/result typography and spacing without changing flow logic.
- [ ] Add mode badges and clearer section titles.
- [ ] Make upload/source hints look like professional workbench guidance instead of raw helper text.
- [ ] Keep mobile layout intact.
- [ ] Run `cd frontend && npm test -- --run App.test.tsx`.
- [ ] Run `cd frontend && npm run build`.

### Task 12: Documentation And Handoff

**Files:**

- Modify: `docs/00-project-brief.md`
- Modify: `docs/01-architecture.md`
- Modify: `docs/02-agent-contracts.md`
- Modify: `docs/05-api-contract.md`
- Modify: `docs/06-export-spec.md`
- Modify: `docs/10-current-status-and-handoff.md`
- Modify: `docs/11-tooling-handoff.md`
- Modify: `.claude/memory/current-progress-and-handoff.md`
- Modify: `.claude/memory/tooling-handoff.md`

**Steps:**

- [ ] Document talent-demand mode as additive V1.3 scope.
- [ ] Document source/legal guardrails.
- [ ] Document project mode contract.
- [ ] Document new artifacts and source coverage matrix.
- [ ] Update handoff/memory after implementation.

---

## Verification Strategy

Keep verification focused and cheap during implementation:

```powershell
python -m pytest tests/unit/test_talent_demand_models.py tests/unit/test_talent_demand_extraction.py tests/unit/test_talent_demand_skills.py tests/unit/test_talent_demand_source_coverage.py -q
python -m pytest tests/unit/test_talent_demand_pipeline.py tests/unit/test_v1_pipeline.py -q
cd frontend; npm test -- --run App.test.tsx
cd frontend; npm run build
git diff --check
```

Do not require real Adzuna, O*NET, ESCO, Tavily, Serper, Brave, Exa, Firecrawl, or Jina credentials in default tests.

Manual acceptance after implementation:

1. Run old `领域建库` topic such as `Agent开发框架`; confirm old export still works.
2. Run talent-demand mode with pasted/uploaded JD samples for `大模型应用开发工程师`; confirm skill matrix and source coverage appear.
3. Export and open Obsidian vault; confirm `skills/`, `roles/`, evidence ledger and README are usable.

---

## Milestone Order

### Milestone A: Safe Foundation

Tasks 1-5. This creates mode contract, models, extraction, skill matrix and source coverage without touching the old V1 pipeline logic.

### Milestone B: Runnable Talent Pipeline

Tasks 6-7. This makes talent-demand mode produce deterministic artifacts and export layout.

### Milestone C: Product Integration

Tasks 8-10. This adds frontend mode switch, source settings visibility and source coverage panel.

### Milestone D: Workbench Polish And Docs

Tasks 11-12. This makes it presentable and keeps handoff state reliable.

---

## Resume-Safe Narrative

After V1.3, the project can be described as:

> Built a LangGraph-based talent-demand intelligence Agent that fuses uploaded JD samples, external research reports, search-provider evidence and occupation/skill taxonomy adapters into an Evidence Ledger. The system extracts role requirements, normalizes skill aliases, builds source coverage metrics, generates skill-demand matrices and exports an Obsidian knowledge vault, while preserving the original domain-knowledge workflow.

