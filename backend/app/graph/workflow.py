"""Minimal adaptive research workflow built on LangGraph."""

from typing import Any

from langgraph.graph import END, StateGraph

from backend.app.schemas import (
    Artifact,
    ArtifactType,
    EvidenceItem,
    ResearchGate,
    ResearchProject,
    ResearchState,
    VerificationStatus,
)


def build_research_graph():
    graph = StateGraph(dict[str, Any])
    graph.add_node("scope_gate", _scope_gate)
    graph.add_node("research_frame_gate", _research_frame_gate)
    graph.add_node("knowledge_map_gate", _knowledge_map_gate)
    graph.add_node("opportunity_gate", _opportunity_gate)
    graph.add_node("export_gate", _export_gate)

    graph.set_entry_point("scope_gate")
    graph.add_edge("scope_gate", "research_frame_gate")
    graph.add_edge("research_frame_gate", "knowledge_map_gate")
    graph.add_edge("knowledge_map_gate", "opportunity_gate")
    graph.add_edge("opportunity_gate", "export_gate")
    graph.add_edge("export_gate", END)
    return graph.compile()


def run_research_workflow(project: ResearchProject) -> ResearchState:
    initial_state = {
        "project": project.model_dump(mode="json"),
        "project_id": project.id,
        "current_gate": ResearchGate.SCOPE.value,
        "evidence": [],
        "artifacts": [],
        "coverage_checklist": {},
        "qa_issues": [],
    }
    raw_state = build_research_graph().invoke(initial_state)
    return ResearchState(
        project_id=raw_state["project_id"],
        current_gate=ResearchGate(raw_state["current_gate"]),
        evidence=[EvidenceItem(**item) for item in raw_state["evidence"]],
        artifacts=[Artifact(**item) for item in raw_state["artifacts"]],
        coverage_checklist=raw_state["coverage_checklist"],
        qa_issues=raw_state["qa_issues"],
    )


def _scope_gate(state: dict[str, Any]) -> dict[str, Any]:
    project = state["project"]
    state["current_gate"] = ResearchGate.RESEARCH_FRAME.value
    state["coverage_checklist"] = {
        "scope_confirmed": True,
        "research_frame": False,
        "knowledge_map": False,
        "opportunity_map": False,
    }
    state["evidence"] = [
        EvidenceItem(
            id="EV-USER-SCOPE",
            project_id=state["project_id"],
            source_title="User project scope",
            snippet=f"User wants to research {project['domain']} with {project['market_scope']} scope.",
            summary="User-provided scope and intent.",
            confidence=1.0,
            verification_status=VerificationStatus.UNVERIFIED,
        ).model_dump(mode="json")
    ]
    return state


def _research_frame_gate(state: dict[str, Any]) -> dict[str, Any]:
    project = state["project"]
    body = (
        f"# {project['domain']} 研究框架\n\n"
        "## 先学什么\n\n"
        "- 行业定义与边界\n"
        "- 市场现状与增长驱动\n"
        "- 玩家角色与交易单位\n"
        "- 内容渠道与信任资产\n"
        "- 机会假设与验证动作\n"
    )
    state["artifacts"].append(
        Artifact(
            id="ART-RESEARCH-FRAME",
            project_id=state["project_id"],
            artifact_type=ArtifactType.RESEARCH_FRAME,
            title="研究框架",
            content_path="00-研究框架/research-frame.md",
            content=body,
            source_evidence_ids=["EV-USER-SCOPE"],
        ).model_dump(mode="json")
    )
    state["coverage_checklist"]["research_frame"] = True
    state["current_gate"] = ResearchGate.KNOWLEDGE_MAP.value
    return state


def _knowledge_map_gate(state: dict[str, Any]) -> dict[str, Any]:
    project = state["project"]
    body = (
        f"# {project['domain']} 行业地图\n\n"
        "## 一级节点\n\n"
        "- 需求侧：用户、场景、痛点、预算\n"
        "- 供给侧：产品、服务、交付、成本\n"
        "- 渠道侧：搜索、内容、本地生活、私域\n"
        "- 风险侧：监管、资质、平台规则、信任成本\n"
    )
    state["artifacts"].append(
        Artifact(
            id="ART-INDUSTRY-MAP",
            project_id=state["project_id"],
            artifact_type=ArtifactType.INDUSTRY_MAP,
            title="行业地图",
            content_path="01-行业地图/industry-map.md",
            content=body,
            source_evidence_ids=["EV-USER-SCOPE"],
        ).model_dump(mode="json")
    )
    state["coverage_checklist"]["knowledge_map"] = True
    state["current_gate"] = ResearchGate.OPPORTUNITY.value
    return state


def _opportunity_gate(state: dict[str, Any]) -> dict[str, Any]:
    project = state["project"]
    body = (
        f"# {project['domain']} 机会地图\n\n"
        "## 第一批机会假设\n\n"
        "- 找出用户痛点强但内容供给不足的细分主题。\n"
        "- 找出信任成本高、但可用案例和证据降低风险的交易单位。\n"
        "- 找出第一周可验证的问题：用户是否搜索、是否咨询、是否愿意付费。\n"
    )
    state["artifacts"].append(
        Artifact(
            id="ART-OPPORTUNITY-MAP",
            project_id=state["project_id"],
            artifact_type=ArtifactType.OPPORTUNITY_MAP,
            title="机会地图",
            content_path="05-机会地图/opportunity-map.md",
            content=body,
            source_evidence_ids=["EV-USER-SCOPE"],
        ).model_dump(mode="json")
    )
    state["coverage_checklist"]["opportunity_map"] = True
    state["current_gate"] = ResearchGate.EXPORT.value
    return state


def _export_gate(state: dict[str, Any]) -> dict[str, Any]:
    state["current_gate"] = ResearchGate.EXPORT.value
    return state
