# Testing Strategy

## Testing Principles

Tests should make the project safe for lower-context agents to modify. Prefer focused tests with clear fixtures over broad tests that require live APIs.

## Required Test Types

### Unit Tests

- Provider interfaces and environment-backed provider factories.
- SQLite repositories, insertion ordering, and FTS retrieval.
- Export writer.
- Schema validation.

### Graph Tests

- Quick and provider-injected research configurations.
- Gate coverage pass and fail paths.
- QA blocking unsupported claims.

Still needed:

- Deep research configuration fixtures.
- Missing evidence retry behavior.
- Human interrupt and resume.

### API Tests

- Project create/list/detail.
- Start run.
- Export package creation.
- Project Q&A.

Still needed:

- Project update/archive.
- Resume run.
- Stream event contract.

### Frontend Tests

- Run workbench state rendering.
- API-backed project creation and run start.
- Project Q&A.
- Export action.

Still needed:

- Editable project creation form.
- Full artifact viewer.

### Golden Tests

Exported Markdown structure must be compared against stable fixtures. Intentional export changes require fixture updates and changelog notes.

## External Services

No automated test should require live LLM or Tavily credentials by default. Use fake providers and deterministic fixtures.
