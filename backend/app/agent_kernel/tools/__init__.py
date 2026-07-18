"""Approved tool set for the V3 Agent Kernel."""

from backend.app.agent_kernel.tool_registry import ToolRegistry
from backend.app.agent_kernel.tools.artifacts import register_artifact_tools
from backend.app.agent_kernel.tools.documents import register_document_tools
from backend.app.agent_kernel.tools.human import register_human_tools
from backend.app.agent_kernel.tools.knowledge_base import register_knowledge_base_tools
from backend.app.agent_kernel.tools.narrative import register_narrative_tools
from backend.app.agent_kernel.tools.search import register_search_tools
from backend.app.agent_kernel.tools.specialists import register_specialist_tools
from backend.app.agent_kernel.tools.state import register_state_tools


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_search_tools(registry)
    register_document_tools(registry)
    register_state_tools(registry)
    register_knowledge_base_tools(registry)
    register_specialist_tools(registry)
    register_artifact_tools(registry)
    register_narrative_tools(registry)
    register_human_tools(registry)
    return registry


__all__ = ["build_default_tool_registry"]
