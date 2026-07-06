"""V2 LangGraph skeleton for the stateful ReAct research architecture.

This graph is intentionally introduced as a side-by-side contract. It does not
replace the runnable V1.6 path yet; it proves the state shape, node names, and
conditional routing needed for the full V2 migration.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from backend.app.agent_state.models import (
    AgentAction,
    AgentDecision,
    CoverageStatus,
    KnowledgeLayerId,
    SectorBreakerState,
    TaskMemory,
)


class V2GraphState(TypedDict, total=False):
    sector_state: dict[str, Any]
    next_action: str
    active_task_id: str | None
    exported: bool
    blocked_reason: str | None


def initialize_context(state: V2GraphState) -> V2GraphState:
    sector_state = SectorBreakerState.model_validate(state["sector_state"])
    if sector_state.current_layer_id is None and sector_state.knowledge_schema.layers:
        sector_state.current_layer_id = sector_state.knowledge_schema.layers[0].id
    return {"sector_state": sector_state.model_dump(mode="json")}


def ingest_external_reports(state: V2GraphState) -> V2GraphState:
    # ReportInternalizer is called by API/service code before this skeleton until
    # document repository access is injected into the V2 graph runtime.
    return state


def master_plan(state: V2GraphState) -> V2GraphState:
    sector_state = SectorBreakerState.model_validate(state["sector_state"])
    layer_id = sector_state.current_layer_id or KnowledgeLayerId.WHAT_WHY
    layer = sector_state.knowledge_schema.layer(layer_id)
    objective = layer.goal if layer else sector_state.meta_context.user_goal
    task = TaskMemory(
        layer_id=layer_id,
        objective=objective,
        checklist=(layer.completion_criteria if layer else []),
    )
    sector_state.add_task_memory(task)
    sector_state.add_decision(AgentDecision(
        action=AgentAction.DISPATCH_TASK,
        reason=f"为 {layer_id.value} 创建 specialist ReAct 任务。",
        layer_id=layer_id,
        next_task_ids=[task.task_id],
    ))
    return {
        "sector_state": sector_state.model_dump(mode="json"),
        "active_task_id": task.task_id,
        "next_action": AgentAction.DISPATCH_TASK.value,
    }


def dispatch_task(state: V2GraphState) -> V2GraphState:
    return state


def specialist_react_loop(state: V2GraphState) -> V2GraphState:
    # The full implementation will call a specialist ReAct loop. The skeleton
    # keeps the graph routable and lets tests validate state transitions first.
    return state


def integrate_state(state: V2GraphState) -> V2GraphState:
    return state


def coverage_judge(state: V2GraphState) -> V2GraphState:
    sector_state = SectorBreakerState.model_validate(state["sector_state"])
    layer_id = sector_state.current_layer_id or KnowledgeLayerId.WHAT_WHY
    layer = sector_state.knowledge_schema.layer(layer_id)
    gaps = sector_state.layer_coverage_gaps(layer_id)
    if layer is not None and not gaps:
        layer.coverage_status = CoverageStatus.SUFFICIENT
        action = AgentAction.CONTINUE
        reason = f"{layer.title} 覆盖已满足。"
    elif sector_state.shared_knowledge.source_memories or sector_state.shared_knowledge.claims:
        if layer is not None:
            layer.coverage_status = CoverageStatus.DEGRADED
        action = AgentAction.DEGRADE
        reason = "已有部分材料但覆盖仍不完整，先降级推进并保留缺口。"
    else:
        if layer is not None:
            layer.coverage_status = CoverageStatus.NEEDS_MORE
        action = AgentAction.SEARCH_AGAIN
        reason = "当前层缺少可用材料，需要继续调研。"
    sector_state.add_decision(AgentDecision(
        action=action,
        reason=reason,
        layer_id=layer_id,
        coverage_gaps=gaps,
    ))
    return {
        "sector_state": sector_state.model_dump(mode="json"),
        "next_action": action.value,
    }


def write_knowledge_base(state: V2GraphState) -> V2GraphState:
    return state


def artifact_review(state: V2GraphState) -> V2GraphState:
    return state


def export_obsidian(state: V2GraphState) -> V2GraphState:
    return {"exported": True}


def wait_for_human_feedback(state: V2GraphState) -> V2GraphState:
    return state


def route_after_coverage(state: V2GraphState) -> str:
    action = state.get("next_action")
    if action == AgentAction.SEARCH_AGAIN.value:
        return "master_plan"
    if action == AgentAction.BLOCK.value:
        return END
    if action == AgentAction.ASK_USER.value:
        return "wait_for_human_feedback"
    return "write_knowledge_base"


def build_v2_react_graph():
    graph = StateGraph(V2GraphState)
    graph.add_node("initialize_context", initialize_context)
    graph.add_node("ingest_external_reports", ingest_external_reports)
    graph.add_node("master_plan", master_plan)
    graph.add_node("dispatch_task", dispatch_task)
    graph.add_node("specialist_react_loop", specialist_react_loop)
    graph.add_node("integrate_state", integrate_state)
    graph.add_node("coverage_judge", coverage_judge)
    graph.add_node("write_knowledge_base", write_knowledge_base)
    graph.add_node("artifact_review", artifact_review)
    graph.add_node("export_obsidian", export_obsidian)
    graph.add_node("wait_for_human_feedback", wait_for_human_feedback)

    graph.set_entry_point("initialize_context")
    graph.add_edge("initialize_context", "ingest_external_reports")
    graph.add_edge("ingest_external_reports", "master_plan")
    graph.add_edge("master_plan", "dispatch_task")
    graph.add_edge("dispatch_task", "specialist_react_loop")
    graph.add_edge("specialist_react_loop", "integrate_state")
    graph.add_edge("integrate_state", "coverage_judge")
    graph.add_conditional_edges(
        "coverage_judge",
        route_after_coverage,
        {
            "master_plan": "master_plan",
            "write_knowledge_base": "write_knowledge_base",
            "wait_for_human_feedback": "wait_for_human_feedback",
            END: END,
        },
    )
    graph.add_edge("write_knowledge_base", "artifact_review")
    graph.add_edge("artifact_review", "export_obsidian")
    graph.add_edge("export_obsidian", "wait_for_human_feedback")
    graph.add_edge("wait_for_human_feedback", END)
    return graph.compile()
