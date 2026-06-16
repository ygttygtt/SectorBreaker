"""Async adaptive research workflow built on LangGraph.

Each gate node emits RunEvent via the provided callback so the frontend
can display real-time progress through SSE.
"""

import asyncio
import time
from typing import Any, Callable, Awaitable

from langgraph.graph import END, StateGraph

from backend.app.providers.interfaces import ChatMessage, LLMProvider, SearchProvider, SearchQuery
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    EvidenceItem,
    ResearchGate,
    ResearchProject,
    ResearchState,
    RunEvent,
    VerificationStatus,
)

# Type alias for the event emitter callback
EventEmitter = Callable[[RunEvent], Awaitable[None]]


async def _emit(emitter: EventEmitter | None, event: RunEvent) -> None:
    """Emit an event if the callback is provided."""
    if emitter is not None:
        await emitter(event)


def build_research_graph(
    search_provider: SearchProvider | None = None,
    llm_provider: LLMProvider | None = None,
    emitter: EventEmitter | None = None,
):
    graph = StateGraph(dict[str, Any])

    graph.add_node("scope_gate", _make_scope_gate(emitter))
    graph.add_node("evidence_gate", _make_evidence_gate(search_provider, emitter))
    graph.add_node("research_frame_gate", _make_research_frame_gate(llm_provider, emitter))
    graph.add_node("knowledge_map_gate", _make_knowledge_map_gate(emitter))
    graph.add_node("opportunity_gate", _make_opportunity_gate(emitter))
    graph.add_node("qa_critic_gate", _make_qa_critic_gate(emitter))
    graph.add_node("export_gate", _make_export_gate(emitter))

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


async def run_research_workflow(
    project: ResearchProject,
    search_provider: SearchProvider | None = None,
    llm_provider: LLMProvider | None = None,
    emitter: EventEmitter | None = None,
    user_guidance: str | None = None,
    user_evidence_items: list[dict[str, Any]] | None = None,
) -> ResearchState:
    initial_state: dict[str, Any] = {
        "project": project.model_dump(mode="json"),
        "project_id": project.id,
        "current_gate": ResearchGate.SCOPE.value,
        "evidence": [],
        "artifacts": [],
        "coverage_checklist": {},
        "qa_issues": [],
        "user_guidance": user_guidance,
        "user_evidence_items": user_evidence_items or [],
    }

    graph = build_research_graph(
        search_provider=search_provider,
        llm_provider=llm_provider,
        emitter=emitter,
    )

    # LangGraph async invoke
    raw_state = await graph.ainvoke(initial_state)

    return ResearchState(
        project_id=raw_state["project_id"],
        current_gate=ResearchGate(raw_state["current_gate"]),
        evidence=[EvidenceItem(**item) for item in raw_state["evidence"]],
        artifacts=[Artifact(**item) for item in raw_state["artifacts"]],
        coverage_checklist=raw_state["coverage_checklist"],
        qa_issues=raw_state["qa_issues"],
    )


# ── Gate factories ────────────────────────────────────────────────


def _make_scope_gate(emitter: EventEmitter | None):
    async def scope_gate(state: dict[str, Any]) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.SCOPE.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate,
            message=f"正在确认研究范围：{project['domain']}",
        ))

        # Inject user-provided evidence if any
        for item in state.get("user_evidence_items", []):
            ev = EvidenceItem(
                id=f"EV-USER-{item.get('id', 'SUPPLEMENT')}",
                project_id=state["project_id"],
                source_title=item.get("source_title", "用户补充信息"),
                snippet=item.get("snippet", ""),
                summary=item.get("summary"),
                confidence=item.get("confidence", 0.8),
                verification_status=VerificationStatus.UNVERIFIED,
            )
            state["evidence"].append(ev.model_dump(mode="json"))

        state["evidence"].append(
            EvidenceItem(
                id="EV-USER-SCOPE",
                project_id=state["project_id"],
                source_title="User project scope",
                snippet=f"User wants to research {project['domain']} with {project['market_scope']} scope.",
                summary="User-provided scope and intent.",
                confidence=1.0,
                verification_status=VerificationStatus.UNVERIFIED,
            ).model_dump(mode="json")
        )

        state["current_gate"] = ResearchGate.RESEARCH_FRAME.value
        state["coverage_checklist"] = {
            "scope_confirmed": True,
            "research_frame": False,
            "knowledge_map": False,
            "opportunity_map": False,
        }

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate,
            message="研究范围已确认",
        ))
        return state

    return scope_gate


def _make_evidence_gate(search_provider: SearchProvider | None, emitter: EventEmitter | None):
    async def evidence_gate(state: dict[str, Any]) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.EVIDENCE.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate,
            message="正在收集行业证据",
        ))

        # Step: Search
        await _emit(emitter, RunEvent(
            event_type="step_start", gate=gate, step="search", agent="Search Scout",
            message=f"正在搜索：{project['domain']} 行业 市场 玩家 机会",
        ))

        if search_provider is not None:
            query = SearchQuery(
                query=f"{project['domain']} 行业 市场 玩家 机会",
                market_scope=project["market_scope"],
                max_results=5,
            )
            try:
                results = await search_provider.search(query)
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

                    await _emit(emitter, RunEvent(
                        event_type="evidence_collected", gate=gate,
                        agent="Search Scout",
                        message=f"找到：{result.title}",
                        data={"evidence_id": evidence.id},
                    ))
            except Exception as exc:
                await _emit(emitter, RunEvent(
                    event_type="error", gate=gate, agent="Search Scout",
                    message=f"搜索失败：{exc}",
                ))
        else:
            await _emit(emitter, RunEvent(
                event_type="step_complete", gate=gate, step="search", agent="Search Scout",
                message="未配置搜索提供商，跳过搜索",
            ))

        await _emit(emitter, RunEvent(
            event_type="step_complete", gate=gate, step="search",
            message=f"证据收集完成，共 {len(state['evidence'])} 条",
        ))

        state["current_gate"] = ResearchGate.RESEARCH_FRAME.value

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate,
            message="证据收集完成",
        ))
        return state

    return evidence_gate


def _make_research_frame_gate(llm_provider: LLMProvider | None, emitter: EventEmitter | None):
    async def research_frame_gate(state: dict[str, Any]) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.RESEARCH_FRAME.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate,
            message="正在生成研究框架",
        ))

        await _emit(emitter, RunEvent(
            event_type="step_start", gate=gate, step="plan", agent="Research Planner",
            message="正在分析领域结构，生成研究框架...",
        ))

        plan = _default_plan()
        if llm_provider is not None:
            try:
                guidance_note = ""
                if state.get("user_guidance"):
                    guidance_note = f"\n用户补充的研究方向：{state['user_guidance']}"

                plan = await llm_provider.complete_structured(
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
                                f"{guidance_note}"
                            ),
                        ),
                    ],
                    response_schema=dict,
                )
            except Exception as exc:
                await _emit(emitter, RunEvent(
                    event_type="error", gate=gate, agent="Research Planner",
                    message=f"LLM 调用失败，使用默认框架：{exc}",
                ))
                plan = _default_plan()

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

        artifact = Artifact(
            id="ART-RESEARCH-FRAME",
            project_id=state["project_id"],
            artifact_type=ArtifactType.RESEARCH_FRAME,
            title="研究框架",
            content_path="00-研究框架/research-frame.md",
            content=body,
            source_evidence_ids=_evidence_ids(state),
        )
        state["artifacts"].append(artifact.model_dump(mode="json"))

        await _emit(emitter, RunEvent(
            event_type="artifact_created", gate=gate, agent="Research Planner",
            message="研究框架已生成",
            data={"artifact_id": artifact.id, "sections": sections},
        ))

        state["coverage_checklist"]["research_frame"] = bool(sections and key_questions)
        state["current_gate"] = ResearchGate.KNOWLEDGE_MAP.value

        await _emit(emitter, RunEvent(
            event_type="step_complete", gate=gate, step="plan", agent="Research Planner",
            message="研究框架生成完成",
        ))

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate,
            message="研究框架生成完成",
        ))
        return state

    return research_frame_gate


def _make_knowledge_map_gate(emitter: EventEmitter | None):
    async def knowledge_map_gate(state: dict[str, Any]) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.KNOWLEDGE_MAP.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate,
            message="正在构建知识地图",
        ))

        artifacts_data = [
            (
                "ART-INDUSTRY-MAP", ArtifactType.INDUSTRY_MAP, "行业地图",
                "01-行业地图/industry-map.md",
                f"# {project['domain']} 行业地图\n\n"
                "## 一级节点\n\n"
                "- 需求侧：用户、场景、痛点、预算\n"
                "- 供给侧：产品、服务、交付、成本\n"
                "- 渠道侧：搜索、内容、本地生活、私域\n"
                "- 风险侧：监管、资质、平台规则、信任成本\n",
            ),
            (
                "ART-MARKET-OVERVIEW", ArtifactType.MARKET_OVERVIEW, "市场现状",
                "02-市场现状/market-overview.md",
                f"# {project['domain']} 市场现状\n\n"
                "- 优先确认市场规模、增长驱动、限制因素和统计口径。\n"
                "- 将事实、观点和待验证假设分开记录。\n",
            ),
            (
                "ART-PLAYER-MAP", ArtifactType.PLAYER_MAP, "玩家与交易单位",
                "03-玩家与交易单位/player-map.md",
                f"# {project['domain']} 玩家与交易单位\n\n"
                "- 拆分提供服务、拥有用户、拥有渠道、负责交付、承担监管的角色。\n"
                "- 继续识别用户真正付钱购买的交易单位。\n",
            ),
            (
                "ART-CONTENT-CHANNELS", ArtifactType.CONTENT_CHANNELS, "内容与渠道",
                "04-内容与渠道/content-channels.md",
                f"# {project['domain']} 内容与渠道\n\n"
                "- 观察搜索关键词、内容平台、私域、本地生活和转介绍。\n"
                "- 区分曝光型、信任型、收藏型、转化型内容。\n",
            ),
        ]

        for art_id, art_type, title, path, content in artifacts_data:
            await _emit(emitter, RunEvent(
                event_type="step_start", gate=gate, step=art_id, agent="Knowledge Mapper",
                message=f"正在生成：{title}",
            ))

            artifact = Artifact(
                id=art_id,
                project_id=state["project_id"],
                artifact_type=art_type,
                title=title,
                content_path=path,
                content=content,
                source_evidence_ids=_evidence_ids(state),
            )
            state["artifacts"].append(artifact.model_dump(mode="json"))

            await _emit(emitter, RunEvent(
                event_type="artifact_created", gate=gate, agent="Knowledge Mapper",
                message=f"{title}已生成",
                data={"artifact_id": art_id},
            ))

        state["coverage_checklist"]["knowledge_map"] = True
        state["current_gate"] = ResearchGate.OPPORTUNITY.value

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate,
            message="知识地图构建完成",
        ))
        return state

    return knowledge_map_gate


def _make_opportunity_gate(emitter: EventEmitter | None):
    async def opportunity_gate(state: dict[str, Any]) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.OPPORTUNITY.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate,
            message="正在分析机会地图",
        ))

        await _emit(emitter, RunEvent(
            event_type="step_start", gate=gate, step="opportunity", agent="Opportunity Analyst",
            message="正在识别机会假设...",
        ))

        artifact = Artifact(
            id="ART-OPPORTUNITY-MAP",
            project_id=state["project_id"],
            artifact_type=ArtifactType.OPPORTUNITY_MAP,
            title="机会地图",
            content_path="05-机会地图/opportunity-map.md",
            content=(
                f"# {project['domain']} 机会地图\n\n"
                "## 第一批机会假设\n\n"
                "- 找出用户痛点强但内容供给不足的细分主题。\n"
                "- 找出信任成本高、但可用案例和证据降低风险的交易单位。\n"
                "- 找出第一周可验证的问题：用户是否搜索、是否咨询、是否愿意付费。\n"
            ),
            source_evidence_ids=_evidence_ids(state),
        )
        state["artifacts"].append(artifact.model_dump(mode="json"))

        await _emit(emitter, RunEvent(
            event_type="artifact_created", gate=gate, agent="Opportunity Analyst",
            message="机会地图已生成",
            data={"artifact_id": artifact.id},
        ))

        state["coverage_checklist"]["opportunity_map"] = True
        state["current_gate"] = ResearchGate.EXPORT.value

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate,
            message="机会地图分析完成",
        ))
        return state

    return opportunity_gate


def _make_qa_critic_gate(emitter: EventEmitter | None):
    async def qa_critic_gate(state: dict[str, Any]) -> dict[str, Any]:
        gate = "qa_critic"

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate,
            message="质量门检查中",
        ))

        await _emit(emitter, RunEvent(
            event_type="step_start", gate=gate, step="qa_check", agent="QA Critic",
            message="正在检查产物完整性和证据引用...",
        ))

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
            await _emit(emitter, RunEvent(
                event_type="error", gate=gate, agent="QA Critic",
                message=f"质量门发现问题：{'; '.join(state['qa_issues'])}",
            ))
        else:
            await _emit(emitter, RunEvent(
                event_type="step_complete", gate=gate, step="qa_check", agent="QA Critic",
                message="质量门检查通过",
            ))

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate,
            message="质量门检查完成",
        ))
        return state

    return qa_critic_gate


def _make_export_gate(emitter: EventEmitter | None):
    async def export_gate(state: dict[str, Any]) -> dict[str, Any]:
        state["current_gate"] = ResearchGate.EXPORT.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate="export",
            message="正在导出知识库",
        ))

        await _emit(emitter, RunEvent(
            event_type="step_start", gate="export", step="write", agent="Export Writer",
            message="正在写入 Obsidian 知识库...",
        ))

        await _emit(emitter, RunEvent(
            event_type="step_complete", gate="export", step="write", agent="Export Writer",
            message=f"已生成 {len(state['artifacts'])} 个产物",
        ))

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate="export",
            message="研究完成！",
        ))
        return state

    return export_gate


# ── Helpers ───────────────────────────────────────────────────────


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
