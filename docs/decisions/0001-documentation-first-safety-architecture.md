# ADR 0001: Documentation-First Safety Architecture

## Status

Accepted

## Context

SectorBreaker will be developed by multiple people and coding agents. Later contributors may not have full architectural context or top-tier reasoning capability. The project needs strong contracts, small ownership boundaries, and stable upgrade points before business features are implemented.

## Decision

Start with documentation and collaboration guardrails before feature code. Require structured Agent contracts, provider interfaces, versioned state/export schemas, and test expectations.

## Consequences

- Initial progress favors safety over visible features.
- Later implementation tasks can be split more reliably.
- Agent output drift is reduced by schema and evidence requirements.
- Changing public contracts requires documentation and tests in the same change.

