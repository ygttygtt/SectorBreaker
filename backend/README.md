# Backend

FastAPI and LangGraph backend for SectorBreaker.

Business logic should be organized around documented contracts:

- API contract: `../docs/05-api-contract.md`
- Graph architecture: `../docs/01-architecture.md`
- Agent contracts: `../docs/02-agent-contracts.md`
- Provider interfaces: `../docs/04-provider-interfaces.md`

Do not call external services directly from graph nodes or route handlers. Use provider interfaces.
