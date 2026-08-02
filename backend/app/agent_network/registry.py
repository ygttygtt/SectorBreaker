"""Agent identity, capability, and transport registry."""

from __future__ import annotations

import os

from backend.app.schemas import AgentManifest, AgentPerformance, AgentTransport
from backend.app.storage.sqlite import SQLiteRepository


class AgentRegistry:
    def __init__(self, manifests: list[AgentManifest]) -> None:
        self._manifests = {manifest.agent_id: manifest for manifest in manifests}
        if len(self._manifests) != len(manifests):
            raise ValueError("agent ids must be unique")

    def list(self) -> list[AgentManifest]:
        return list(self._manifests.values())

    def get(self, agent_id: str) -> AgentManifest:
        try:
            return self._manifests[agent_id]
        except KeyError as exc:
            raise KeyError(f"agent not registered: {agent_id}") from exc

    def replace(self, manifest: AgentManifest) -> None:
        if manifest.agent_id not in self._manifests:
            raise KeyError(f"agent not registered: {manifest.agent_id}")
        self._manifests[manifest.agent_id] = manifest


def build_demo_agent_registry(
    repository: SQLiteRepository,
    project_id: str,
    *,
    a2a_endpoint: str | None = None,
    a2a_available: bool | None = None,
    a2a_capabilities: list[str] | None = None,
) -> AgentRegistry:
    endpoint = (a2a_endpoint or os.getenv("SECTORBREAKER_A2A_RESEARCHER_URL") or "").strip() or None
    remote_available = bool(endpoint) if a2a_available is None else a2a_available
    remote_capabilities = a2a_capabilities or ["research_ecosystem", "web_search", "evidence_extract"]

    def performance(agent_id: str) -> AgentPerformance:
        return repository.get_agent_performance(project_id, agent_id)

    manifests = [
        AgentManifest(
            agent_id="foundation_researcher_local",
            display_name="Foundation Researcher",
            role="researcher",
            capabilities=["research_foundations", "web_search", "evidence_extract"],
            tool_allowlist=["search_web", "retrieve_project_memory", "inspect_evidence"],
            concurrency_limit=1,
            cost_tier=1,
            performance=performance("foundation_researcher_local"),
        ),
        AgentManifest(
            agent_id="ecosystem_researcher_a2a",
            display_name="A2A Ecosystem Researcher",
            role="researcher",
            capabilities=remote_capabilities,
            tool_allowlist=["search_web", "inspect_evidence"],
            concurrency_limit=1,
            cost_tier=1,
            transport=AgentTransport.A2A,
            endpoint=endpoint,
            protocol_version="1.0",
            available=remote_available,
            performance=performance("ecosystem_researcher_a2a"),
        ),
        AgentManifest(
            agent_id="ecosystem_researcher_local",
            display_name="Local Ecosystem Researcher",
            role="researcher",
            capabilities=["research_ecosystem", "web_search", "evidence_extract"],
            tool_allowlist=["search_web", "retrieve_project_memory", "inspect_evidence"],
            concurrency_limit=1,
            cost_tier=2,
            performance=performance("ecosystem_researcher_local"),
        ),
        AgentManifest(
            agent_id="counterevidence_verifier_local",
            display_name="Counterevidence Verifier",
            role="verifier",
            capabilities=["verify_claims", "counterevidence", "web_search"],
            tool_allowlist=["search_web", "retrieve_project_memory", "inspect_evidence"],
            concurrency_limit=1,
            cost_tier=2,
            performance=performance("counterevidence_verifier_local"),
        ),
        AgentManifest(
            agent_id="knowledge_editor_local",
            display_name="Knowledge Editor",
            role="knowledge_editor",
            capabilities=["synthesize_starter_note", "propose_change_set"],
            tool_allowlist=["retrieve_project_memory", "propose_change_set"],
            concurrency_limit=1,
            cost_tier=2,
            performance=performance("knowledge_editor_local"),
        ),
    ]
    return AgentRegistry(manifests)
