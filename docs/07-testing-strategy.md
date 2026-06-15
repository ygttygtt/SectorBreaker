# Testing Strategy

## Testing Principles

Tests should make the project safe for lower-context agents to modify. Prefer focused tests with clear fixtures over broad tests that require live APIs.

## Required Test Types

### Unit Tests

- Provider interfaces with fake implementations.
- SQLite repositories.
- Export writer.
- FTS retrieval.
- Schema validation.

### Graph Tests

- Quick, standard, and deep research configurations.
- Gate coverage pass and fail paths.
- Missing evidence retry.
- Human interrupt and resume.
- QA blocking unsupported claims.

### API Tests

- Project CRUD.
- Start run.
- Resume run.
- Stream event contract.
- Export package creation.
- Project Q&A.

### Frontend Tests

- Project creation form.
- Run cockpit state rendering.
- Evidence list.
- Artifact viewer.
- Export action.

### Golden Tests

Exported Markdown structure must be compared against stable fixtures. Intentional export changes require fixture updates and changelog notes.

## External Services

No automated test should require live LLM or Tavily credentials by default. Use fake providers and deterministic fixtures.
