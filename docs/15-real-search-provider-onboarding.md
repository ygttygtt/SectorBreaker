# Real Search Provider Onboarding

## Purpose

This checklist is the shortest path from "the search stack code exists" to
"real providers are connected and the project is genuinely using web search".

Use this after reading:

1. `AGENTS.md`
2. `README.md`
3. `docs/04-provider-interfaces.md`
4. `docs/05-api-contract.md`
5. `docs/14-search-and-report-ingestion-design.md`

## What Counts As Success

Search onboarding is complete only when all of the following are true:

1. At least one real search provider key is configured.
2. `GET /api/config/search` reports `configured=true`.
3. `POST /api/config/search/test` returns `success=true` and `result_count > 0`.
4. `python run_search_smoke_test.py` prints `result_count > 0`.
5. A real project run writes open-web evidence into the evidence ledger.

If any of these is missing, the bottom layer is improved but the real search
capability is not yet fully proven.

## Supported Providers

### Search providers

- Tavily
- Serper
- Brave Search API
- Exa

### Extraction providers

- `http` fallback
- Firecrawl
- Jina Reader-style extraction

## Recommended Setup Paths

### Path A: UI-first onboarding

Best when you want to avoid editing `.env` manually.

1. Start the backend:

   ```bash
   conda activate sectorbreaker
   uvicorn backend.app.api.app:app --host 127.0.0.1 --port 8000 --reload
   ```

2. Start the frontend:

   ```bash
   cd frontend
   npm run dev -- --host 127.0.0.1 --port 3000
   ```

3. Open the landing page and confirm it currently shows the explicit
   unconfigured warning if no search key has been filled yet.
4. Open the `LLM 设置` panel.
5. Fill at least one of:
   - `Tavily API Key`
   - `Serper API Key`
   - `Brave API Key`
   - `Exa API Key`
6. Choose `search_provider_mode`:
   - `auto`: recommended default
   - `multi`: aggregate all configured providers
   - `tavily` / `serper` / `brave` / `exa`: force one provider
7. Choose extraction mode:
   - `http`: simplest default
   - `firecrawl`: requires `FIRECRAWL_API_KEY`
   - `jina`: no key required in the current baseline
8. Save the search config.
9. Click `测试搜索链路`.
10. Confirm the result card shows:
    - provider names
    - `结果数 > 0`
    - first result preview
    - extracted page preview when extraction succeeds

### Path B: `.env`-first onboarding

Best when you want local config under a file and CLI parity immediately.

1. Create `.env` from the template:

   ```bash
   Copy-Item .env.example .env
   ```

   Or generate a minimal provider-specific snippet:

   ```bash
   python generate_search_env_template.py tavily http
   ```

   Or write `.env` directly:

   ```bash
   python generate_search_env_template.py tavily http --write .env
   ```

2. Fill at least one search key:

   ```env
   SEARCH_PROVIDER_MODE=auto

   TAVILY_API_KEY=...
   SERPER_API_KEY=
   BRAVE_API_KEY=
   EXA_API_KEY=
   ```

3. Optional extraction config:

   ```env
   CONTENT_EXTRACTION_PROVIDER=http
   ```

   Or:

   ```env
   CONTENT_EXTRACTION_PROVIDER=firecrawl
   FIRECRAWL_API_KEY=...
   ```

   Or:

   ```env
   CONTENT_EXTRACTION_PROVIDER=jina
   ```

4. Start the backend. The app will load `.env` automatically.
5. Use the API and CLI checks below.

## Verification Sequence

Run these in order. Do not skip directly to a full project run.

### Step 1: Read config status

```bash
curl http://127.0.0.1:8000/api/config/search
```

Expected signals:

- `configured` is `true`
- `providers` is non-empty
- `status_message` says search is ready
- `missing_configuration` matches the current mode instead of blindly listing every unused provider key

### Step 2: Live search test

```bash
curl -X POST http://127.0.0.1:8000/api/config/search/test ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"AI agent market map\",\"market_scope\":\"mixed\",\"max_results\":3}"
```

Expected signals:

- `success` is `true`
- `result_count` is greater than `0`
- `providers` contains the provider you configured

Useful stricter checks:

```bash
curl -X POST http://127.0.0.1:8000/api/config/search/test ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"AI agent market map\",\"market_scope\":\"china\",\"source_policy\":\"reliable_only\",\"allowed_domains\":[\"gov.cn\",\"stats.gov.cn\"],\"blocked_domains\":[\"medium.com\"]}"
```

This confirms source-policy and domain constraints are actually affecting the
search call.

### Step 3: CLI smoke test

```bash
python run_search_smoke_test.py
```

Expected signals:

- `result_count > 0`
- `first_result_source_quality`
- `first_result_verification_status`

Optional stricter CLI run:

```bash
$env:SECTORBREAKER_SMOKE_SOURCE_POLICY="reliable_only"
$env:SECTORBREAKER_SMOKE_ALLOWED_DOMAINS="gov.cn,stats.gov.cn"
$env:SECTORBREAKER_SMOKE_BLOCKED_DOMAINS="medium.com,substack.com"
python run_search_smoke_test.py
```

### Step 4: End-to-end acceptance script

```bash
python run_real_search_acceptance.py
```

This script automates:

- config-status verification
- live search test
- project creation
- `auto_run=true` execution
- evidence-ledger writeback confirmation

Useful environment variables:

```bash
$env:SECTORBREAKER_ACCEPTANCE_QUERY="AI agent market map"
$env:SECTORBREAKER_ACCEPTANCE_SOURCE_POLICY="open_web"
$env:SECTORBREAKER_ACCEPTANCE_ALLOWED_DOMAINS="gov.cn,stats.gov.cn"
$env:SECTORBREAKER_ACCEPTANCE_BLOCKED_DOMAINS="medium.com"
```

### Step 5: Real project evidence writeback

1. Create a new project.
2. Start a run with `auto_run=true`.
3. After completion, open:

   - `GET /api/projects/{project_id}/evidence`
   - the frontend evidence list

4. Confirm there are open-web search evidence items, not only assistant-brief or
   document-ingested evidence.

This is the final manual proof that the system is not only able to search, but
is actually feeding search results into the workflow.

In the current baseline, the strongest indicator is:

- evidence items with `source_channel = search`

## Provider Selection Guidance

### Start simple

Recommended first real setup:

- `SEARCH_PROVIDER_MODE=tavily`
- one provider key only
- `CONTENT_EXTRACTION_PROVIDER=http`

Reason:

- fewer moving parts
- easiest failure isolation
- enough to prove the search stack is live

Shortcut:

```bash
python generate_search_env_template.py tavily http
```

### Then expand

Recommended second step after the first provider works:

- add a second provider
- switch to `multi`
- rerun `/api/config/search/test`

This verifies the aggregation path before it is used in important research runs.

## Failure Diagnosis

### `configured=false`

Check:

- `.env` exists if you are using file-based config
- at least one real API key is filled
- the UI save action returned success if you used runtime config

### `success=false` from `/api/config/search/test`

Check:

- `/api/config/search` -> `missing_configuration`
- `/api/config/search` -> `diagnostics`
- provider endpoint overrides
- provider account quota or auth failures

### Extraction falls back unexpectedly

Current expected behavior:

- requesting `firecrawl` without `FIRECRAWL_API_KEY` falls back to `http`
- the diagnostics output should explain this

### Search works but no evidence is written in a real run

Check:

- the run actually reached completion
- the project did not use `user_materials_only`
- the workflow evidence list contains search results before export
- LLM output and QA did not block the run in a way that skipped downstream work

## Current Limitation

The current repository state provides the full onboarding path, but this machine
still needs real provider keys before the final acceptance proof can be claimed.
