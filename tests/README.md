# Tests

Tests should be deterministic and runnable without live LLM or Tavily credentials by default.

Planned groups:

- `unit/`: schemas, repositories, providers, exporters.
- `graph/`: LangGraph gate, retry, interrupt, and QA behavior.
- `api/`: FastAPI contract tests.
- `frontend/`: component and workflow tests.
- `fixtures/`: fake provider responses and golden exports.

See `../docs/07-testing-strategy.md`.

