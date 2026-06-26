# Runnable V1 Acceptance

This checklist proves SectorBreaker V1 with real configured services, not fake providers.

## Prerequisites

Start the backend with repository-root `.env` loaded automatically:

```bash
python -m uvicorn backend.app.api.app:app --host 127.0.0.1 --port 8030
```

Required configuration:

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `TAVILY_API_KEY`

The UI runtime config can also provide these values, but `.env` is the simplest acceptance path.

## Command

```bash
$env:SECTORBREAKER_API_BASE_URL="http://127.0.0.1:8030"
$env:SECTORBREAKER_ACCEPTANCE_QUERY="Agent development latest trends"
$env:SECTORBREAKER_ACCEPTANCE_PROJECT_TITLE="Agent Development Acceptance"
$env:SECTORBREAKER_ACCEPTANCE_PROJECT_DOMAIN="Agent development"
python run_real_search_acceptance.py
```

## Required Pass Conditions

The script must confirm:

- LLM config is available.
- Tavily-backed search config is available.
- live search returns at least one result.
- a project run completes.
- search-channel evidence is written.
- V1 knowledge artifacts exist:
  - `00-领域总览.md`
  - `01-入门路线.md`
  - `02-核心概念.md`
  - `03-玩家与工具地图.md`
  - `04-趋势与证据.md`
  - `05-问题与机会.md`
  - `99-待验证问题.md`
- Obsidian export manifest includes:
  - all V1 knowledge artifacts;
  - `_sources/evidence-ledger.md`;
  - `manifest.json`.

## Failure Handling

If LLM config fails, check `/api/config/llm` and `.env`.

If search config fails, check `/api/config/search`, `TAVILY_API_KEY`, and `SEARCH_PROVIDER_MODE`.

If the run fails after search succeeds, inspect `/api/runs/{run_id}/snapshot` for the failed stage and error event.

