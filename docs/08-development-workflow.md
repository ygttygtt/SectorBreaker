# Development Workflow

## Environment

Use conda for Python environment isolation.

Recommended environment:

```bash
conda env create -f environment.yml
conda activate sectorbreaker
```

Frontend uses Node.js with Vite + React + TypeScript.

Backend development server:

```bash
uvicorn backend.app.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Frontend development server:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3000
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000` by default.
When port 8000 is already occupied, set `VITE_API_PROXY_TARGET`, for example:

```bash
$env:VITE_API_PROXY_TARGET="http://127.0.0.1:8010"
npm run dev -- --host 127.0.0.1 --port 3010
```

## Local Configuration

Secrets go in `.env` or `.env.local`; never commit them.

The backend app and `run_search_smoke_test.py` automatically load `.env` from
the repository root during local development.

Search runtime config that is saved from the UI is also persisted locally beside
the SQLite database as `*.runtime-config.json`, so backend restarts do not clear
the current provider setup.

Expected keys:

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `TAVILY_API_KEY`
- `SERPER_API_KEY`
- `BRAVE_API_KEY`
- `CONTENT_EXTRACTION_PROVIDER` (`http` | `firecrawl` | `jina`)
- `FIRECRAWL_API_KEY`
- `FIRECRAWL_ENDPOINT`
- `JINA_READER_ENDPOINT_PREFIX`

Content extraction selection:

- default is `http`, which uses a local HTTP fetch + HTML cleaning fallback;
- set `CONTENT_EXTRACTION_PROVIDER=firecrawl` and `FIRECRAWL_API_KEY` to use Firecrawl scraping;
- set `CONTENT_EXTRACTION_PROVIDER=jina` to use the Jina Reader-style extractor;
- when `firecrawl` is selected but `FIRECRAWL_API_KEY` is missing, the system falls back to `http`.

Runtime paths can be overridden with:

- `SECTORBREAKER_DB_PATH`
- `SECTORBREAKER_EXPORT_ROOT`

## Task Workflow

1. Read `AGENTS.md` and relevant docs.
2. Confirm the files you own.
3. Update docs first when changing contracts.
4. Write or update tests.
5. Implement the smallest safe change.
6. Run relevant verification.
7. Check diffs for unrelated changes.
8. Commit.

## Review Checklist

- Does the change preserve provider boundaries?
- Are Agent outputs structured?
- Are factual claims evidence-linked?
- Are public schemas documented?
- Are tests deterministic without live external APIs?
- Does generated output stay out of git?
