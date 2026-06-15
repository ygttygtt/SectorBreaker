# Development Workflow

## Environment

Use conda for Python environment isolation.

Recommended environment:

```bash
conda env create -f environment.yml
conda activate sectorbreaker
```

Frontend uses Node.js with Vite + React + TypeScript.

## Local Configuration

Secrets go in `.env` or `.env.local`; never commit them.

Expected keys:

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `TAVILY_API_KEY`

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
