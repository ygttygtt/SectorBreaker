# Backend App Skeleton

Planned module boundaries:

- `api/`: FastAPI routes and request/response schemas.
- `core/`: configuration, logging, errors.
- `graph/`: LangGraph state, gates, supervisor, and worker nodes.
- `providers/`: LLM, search, retrieval, and export provider implementations.
- `storage/`: SQLite repositories and migrations.
- `schemas/`: shared Pydantic models.

Keep each module small and documented before adding behavior.
