"""Minimal adaptive research workflow built on LangGraph."""

import asyncio
from typing import Any

from langgraph.graph import END, StateGraph

from backend.app.providers.interfaces import ChatMessage, LLMProvider, SearchProvider, SearchQuery
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    EvidenceItem,
    ResearchGate,
    ResearchProject,
    ResearchState,
    VerificationStatus,
)


def build_research_graph(
    search_provider: SearchProvider | None = None,
    llm_provider: LLMProvider | None = None,
):
    graph = StateGraph(dict[str, Any])
    graph.add_node("scope_gate", _scope_gate)
    graph.add_node("evidence_gate", _make_evidence_gate(search_provider))
    graph.add_node("research_frame_gate", _make_research_frame_gate(llm_provider))
    graph.add_node("knowledge_map_gate", _knowledge_map_gate)
    graph.add_node("opportunity_gate", _opportunity_gate)
    graph.add_node("qa_critic_gate", _qa_critic_gate)
    graph.add_node("export_gate", _export_gate)

    graph.set_entry_point("scope_gate")
    graph.add_edge("scope_gate", "evidence_gate")
    graph.add_edge("evidence_gate", "research_frame_gate")
    graph.add_edge("research_frame_gate", "knowledge_map_gate")
    graph.add_edge("knowledge_map_gate", "opportunity_gate")
    graph.add_edge("opportunity_gate", "qa_critic_gate")
    graph.add_conditional_edges(
        "qa_critic_gate",
        _route_after_qa,
        {"export": "export_gate", "blocked": END},
    )
    graph.add_edge("export_gate", END)
    return graph.compile()


def run_research_workflow(
    project: ResearchProject,
    search_provider: SearchProvider | None = None,
    llm_provider: LLMProvider | None = None,
) -> ResearchState:
    initial_state = {
        "project": project.model_dump(mode="json"),
        "project_id": project.id,
        "current_gate": ResearchGate.SCOPE.value,
        "evidence": [],
        "artifacts": [],
        "coverage_checklist": {},
        "qa_issues": [],
    }
    raw_state = build_research_graph(
        search_provider=search_provider,
        llm_provider=llm_provider,
    ).invoke(initial_state)
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


def _make_evidence_gate(search_provider: SearchProvider | None):
    def evidence_gate(state: dict[str, Any]) -> dict[str, Any]:
        if search_provider is None:
            return state
        project = state["project"]
        query = SearchQuery(
            query=f"{project['domain']} 行业 市场 玩家 机会",
            market_scope=project["market_scope"],
            max_results=5,
        )
        results = asyncio.run(search_provider.search(query))
        for index, result in enumerate(results, start=1):
            evidence = EvidenceItem(
                id=f"EV-SEARCH-{index:03d}",
                project_id=state["project_id"],
                source_title=result.title,
                source_url=result.url,
                source_type="web",
                snippet=result.snippet,
                summary=result.snippet,
                confidence=0.65,
                verification_status=VerificationStatus.PARTIALLY_VERIFIED,
            )
            state["evidence"].append(evidence.model_dump(mode="json"))
        return state

    return evidence_gate


def _make_research_frame_gate(llm_provider: LLMProvider | None):
    def research_frame_gate(state: dict[str, Any]) -> dict[str, Any]:
        project = state["project"]
        plan = _default_plan()
        if llm_provider is not None:
            plan = asyncio.run(
                llm_provider.complete_structured(
                    messages=[
                        ChatMessage(
                            role="system",
                            content="你是行业研究规划 Agent。只返回 JSON。",
                        ),
                        ChatMessage(
                            role="user",
                            content=(
                                f"为 {project['domain']} 生成研究框架。"
                                "JSON 字段：sections、key_questions。"
                            ),
                        ),
                    ],
                    response_schema=dict,
                )
            )
        sections = [item for item in plan.get("sections", []) if item]
        key_questions = [item for item in plan.get("key_questions", []) if item]
        section_body = "\n".join(f"- {item}" for item in sections)
        question_body = "\n".join(f"- {item}" for item in key_questions)
        body = (
            f"# {project['domain']} 研究框架\n\n"
            "## 先学什么\n\n"
            f"{section_body}\n\n"
            "## 关键问题\n\n"
            f"{question_body}\n"
        )
        state["artifacts"].append(
            Artifact(
                id="ART-RESEARCH-FRAME",
                project_id=state["project_id"],
                artifact_type=ArtifactType.RESEARCH_FRAME,
                title="研究框架",
                content_path="00-研究框架/research-frame.md",
                content=body,
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json")
        )
        state["coverage_checklist"]["research_frame"] = bool(sections and key_questions)
        state["current_gate"] = ResearchGate.KNOWLEDGE_MAP.value
        return state

    return research_frame_gate


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
            source_evidence_ids=_evidence_ids(state),
        ).model_dump(mode="json")
    )
    state["artifacts"].extend(
        [
            Artifact(
                id="ART-MARKET-OVERVIEW",
                project_id=state["project_id"],
                artifact_type=ArtifactType.MARKET_OVERVIEW,
                title="市场现状",
                content_path="02-市场现状/market-overview.md",
                content=(
                    f"# {project['domain']} 市场现状\n\n"
                    "- 优先确认市场规模、增长驱动、限制因素和统计口径。\n"
                    "- 将事实、观点和待验证假设分开记录。\n"
                ),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json"),
            Artifact(
                id="ART-PLAYER-MAP",
                project_id=state["project_id"],
                artifact_type=ArtifactType.PLAYER_MAP,
                title="玩家与交易单位",
                content_path="03-玩家与交易单位/player-map.md",
                content=(
                    f"# {project['domain']} 玩家与交易单位\n\n"
                    "- 拆分提供服务、拥有用户、拥有渠道、负责交付、承担监管的角色。\n"
                    "- 继续识别用户真正付钱购买的交易单位。\n"
                ),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json"),
            Artifact(
                id="ART-CONTENT-CHANNELS",
                project_id=state["project_id"],
                artifact_type=ArtifactType.CONTENT_CHANNELS,
                title="内容与渠道",
                content_path="04-内容与渠道/content-channels.md",
                content=(
                    f"# {project['domain']} 内容与渠道\n\n"
                    "- 观察搜索关键词、内容平台、私域、本地生活和转介绍。\n"
                    "- 区分曝光型、信任型、收藏型、转化型内容。\n"
                ),
                source_evidence_ids=_evidence_ids(state),
            ).model_dump(mode="json"),
        ]
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
            source_evidence_ids=_evidence_ids(state),
        ).model_dump(mode="json")
    )
    state["coverage_checklist"]["opportunity_map"] = True
    state["current_gate"] = ResearchGate.EXPORT.value
    return state


def _export_gate(state: dict[str, Any]) -> dict[str, Any]:
    state["current_gate"] = ResearchGate.EXPORT.value
    return state


def _qa_critic_gate(state: dict[str, Any]) -> dict[str, Any]:
    required_coverage = ["scope_confirmed", "research_frame", "knowledge_map", "opportunity_map"]
    missing = [item for item in required_coverage if not state["coverage_checklist"].get(item)]
    if missing:
        state["qa_issues"].append(f"研究框架或关键产物 coverage 不完整: {', '.join(missing)}")

    unsupported = [
        artifact["id"]
        for artifact in state["artifacts"]
        if not artifact.get("source_evidence_ids")
    ]
    if unsupported:
        state["qa_issues"].append(f"存在缺少证据引用的产物: {', '.join(unsupported)}")

    if state["qa_issues"]:
        state["current_gate"] = ResearchGate.OPPORTUNITY.value
    return state


def _route_after_qa(state: dict[str, Any]) -> str:
    if state["qa_issues"]:
        return "blocked"
    return "export"


def _default_plan() -> dict[str, list[str]]:
    return {
        "sections": [
            "行业定义与边界",
            "市场现状与增长驱动",
            "玩家角色与交易单位",
            "内容渠道与信任资产",
            "机会假设与验证动作",
        ],
        "key_questions": [
            "这个领域的用户为什么付费？",
            "哪些数据口径容易混淆？",
            "哪些环节最影响信任和转化？",
        ],
    }


def _evidence_ids(state: dict[str, Any]) -> list[str]:
    return [item["id"] for item in state["evidence"]]
