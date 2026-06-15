# SectorBreaker Project Brief

## Product Goal

SectorBreaker is a local-first research workbench that helps a user break into an unfamiliar domain faster than ordinary search or a one-shot AI answer. It turns scattered sources into a structured industry cognition system: what to learn, what the current state looks like, where demand exists, and which opportunities are worth validating.

## First Version Scope

- Single-user local workbench.
- FastAPI backend with LangGraph adaptive research workflow.
- Vite + React + TypeScript frontend.
- SQLite for project metadata, run state, evidence metadata, and FTS project Q&A.
- Markdown and Obsidian-friendly knowledge base export.
- OpenAI-compatible LLM configuration.
- Tavily as the default search provider through a replaceable interface.

## Explicit Non-Goals For V1

- No multi-user account system.
- No cloud task scheduler.
- No automatic subscription monitoring or weekly report daemon.
- No full vector RAG implementation.
- No scraping of login-gated or platform-restricted social content.
- No production deployment automation.

## Core User Journey

1. User creates a research project with domain, market scope, and depth.
2. System proposes the research frame and learning path.
3. User confirms or edits the frame.
4. Agents gather sources, normalize evidence, and identify gaps.
5. System builds industry map, key players, transaction units, content/channel patterns, risk boundaries, and opportunity hypotheses.
6. User reviews stage outputs.
7. System exports an Obsidian-compatible knowledge base and supports lightweight project Q&A.

## Roadmap

- V1: Adaptive workflow, evidence-linked research output, Obsidian export, SQLite FTS Q&A.
- V2: Embeddings, vector retrieval, stronger RAG, source re-ranking, richer citation audit.
- V3: Monitoring jobs, weekly reports, team collaboration, permissions, cloud deployment.
