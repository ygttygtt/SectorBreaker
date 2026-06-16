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


async def _llm_generate(
    llm_provider: LLMProvider | None,
    system_prompt: str,
    user_prompt: str,
    fallback: dict | str,
    emitter: EventEmitter | None,
    gate: str,
    agent: str,
) -> dict | str:
    """Call LLM with fallback to template on failure."""
    if llm_provider is None:
        return fallback
    try:
        result = await llm_provider.complete_structured(
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ],
            response_schema=dict if isinstance(fallback, dict) else str,
        )
        return result
    except Exception as exc:
        await _emit(emitter, RunEvent(
            event_type="error", gate=gate, agent=agent,
            message=f"LLM 调用失败，使用默认内容：{exc}",
        ))
        return fallback


def build_research_graph(
    search_provider: SearchProvider | None = None,
    llm_provider: LLMProvider | None = None,
    emitter: EventEmitter | None = None,
):
    graph = StateGraph(dict[str, Any])

    graph.add_node("scope_gate", _make_scope_gate(llm_provider, emitter))
    graph.add_node("evidence_gate", _make_evidence_gate(search_provider, emitter))
    graph.add_node("research_frame_gate", _make_research_frame_gate(llm_provider, emitter))
    graph.add_node("knowledge_map_gate", _make_knowledge_map_gate(llm_provider, emitter))
    graph.add_node("opportunity_gate", _make_opportunity_gate(llm_provider, emitter))
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


def _make_scope_gate(llm_provider: LLMProvider | None, emitter: EventEmitter | None):
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

        # Use LLM to analyze domain scope and identify key boundaries
        await _emit(emitter, RunEvent(
            event_type="step_start", gate=gate, step="scope_analysis", agent="Research Planner",
            message="正在分析领域边界和研究范围...",
        ))

        scope_analysis = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是行业研究规划 Agent。用户想研究一个领域，你需要分析这个领域的边界。"
                "只返回 JSON，字段：domain_definition（领域定义）, boundaries（边界说明）, "
                "common_confusions（常见混淆点列表）, recommended_scope（建议研究范围）。"
            ),
            user_prompt=(
                f"领域：{project['domain']}\n"
                f"市场范围：{project['market_scope']}\n"
                f"研究深度：{project['depth']}\n"
                f"{'用户补充：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            fallback={
                "domain_definition": f"{project['domain']}行业研究",
                "boundaries": "需要进一步明确",
                "common_confusions": ["市场口径不统一", "数据来源不一致"],
                "recommended_scope": "先从行业概况和主要玩家开始",
            },
            emitter=emitter, gate=gate, agent="Research Planner",
        )

        if isinstance(scope_analysis, dict):
            summary = scope_analysis.get("domain_definition", project['domain'])
            boundaries = scope_analysis.get("boundaries", "")
            confusions = scope_analysis.get("common_confusions", [])
            scope_content = f"{summary}。边界：{boundaries}。常见混淆：{', '.join(str(c) for c in confusions)}"
        else:
            scope_content = str(scope_analysis)

        await _emit(emitter, RunEvent(
            event_type="artifact_created", gate=gate, agent="Research Planner",
            message=f"范围分析完成：{scope_content[:80]}...",
        ))

        state["current_gate"] = ResearchGate.EVIDENCE.value
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

        # Step 1: Search for market overview
        await _emit(emitter, RunEvent(
            event_type="step_start", gate=gate, step="search_market", agent="Search Scout",
            message=f"正在搜索：{project['domain']} 行业概况 市场规模",
        ))

        search_queries = [
            f"{project['domain']} 行业概况 市场规模 趋势",
            f"{project['domain']} 主要玩家 竞争格局",
            f"{project['domain']} 用户痛点 机会",
        ]

        if search_provider is not None:
            for query_idx, query_text in enumerate(search_queries):
                query = SearchQuery(
                    query=query_text,
                    market_scope=project["market_scope"],
                    max_results=5,
                )
                try:
                    results = await search_provider.search(query)
                    for index, result in enumerate(results, start=1):
                        evidence = EvidenceItem(
                            id=f"EV-SEARCH-{query_idx}-{index:03d}",
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
                        message=f"搜索失败（{query_text}）：{exc}",
                    ))
        else:
            await _emit(emitter, RunEvent(
                event_type="step_complete", gate=gate, step="search", agent="Search Scout",
                message="未配置搜索提供商，跳过在线搜索",
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

        plan = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是行业研究规划 Agent。为用户指定的行业生成研究框架。"
                "只返回 JSON，字段：sections（研究板块列表）, key_questions（关键问题列表）, "
                "learning_path（学习路径列表）。"
            ),
            user_prompt=(
                f"为 {project['domain']} 生成研究框架。"
                f"市场范围：{project['market_scope']}。"
                f"{'用户补充方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            fallback=_default_plan(),
            emitter=emitter, gate=gate, agent="Research Planner",
        )

        if isinstance(plan, dict):
            sections = [item for item in plan.get("sections", []) if item]
            key_questions = [item for item in plan.get("key_questions", []) if item]
        else:
            plan = _default_plan()
            sections = plan["sections"]
            key_questions = plan["key_questions"]

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


def _make_knowledge_map_gate(llm_provider: LLMProvider | None, emitter: EventEmitter | None):
    async def knowledge_map_gate(state: dict[str, Any]) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.KNOWLEDGE_MAP.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate,
            message="正在构建知识地图",
        ))

        # Define artifacts to generate with LLM
        artifacts_spec = [
            (
                "ART-INDUSTRY-MAP", ArtifactType.INDUSTRY_MAP, "行业地图",
                "01-行业地图/industry-map.md",
                "行业地图与产业链结构",
                "你是行业研究 Agent。为指定行业生成知识地图。只返回 JSON，字段：title, "
                "content（Markdown 格式，包含一级节点、二级节点，标注供给侧/需求侧/渠道/风险边界）。"
                "至少包含 4 个一级节点，每个一级节点下 2-3 个二级节点。",
            ),
            (
                "ART-MARKET-OVERVIEW", ArtifactType.MARKET_OVERVIEW, "市场现状",
                "02-市场现状/market-overview.md",
                "市场规模、增长驱动与约束",
                "你是市场分析 Agent。为指定行业生成市场现状分析。只返回 JSON，字段：title, "
                "content（Markdown 格式，包含市场规模估算、增长驱动、限制因素、数据口径说明）。"
                "区分事实、推测和观点。",
            ),
            (
                "ART-PLAYER-MAP", ArtifactType.PLAYER_MAP, "玩家与交易单位",
                "03-玩家与交易单位/player-map.md",
                "玩家角色、商业逻辑与交易单位",
                "你是竞品分析 Agent。为指定行业生成玩家与交易单位分析。只返回 JSON，字段：title, "
                "content（Markdown 格式，按角色分类：提供服务者、拥有用户者、拥有渠道者、"
                "掌握关键资源者、负责交付者、监管者。每类给出代表玩家、商业价值、议价能力）。"
                "同时识别主要交易单位（用户真正付钱购买的东西）。",
            ),
            (
                "ART-CONTENT-CHANNELS", ArtifactType.CONTENT_CHANNELS, "内容与渠道",
                "04-内容与渠道/content-channels.md",
                "内容生态、获客渠道与转化路径",
                "你是内容生态分析 Agent。为指定行业生成内容与渠道分析。只返回 JSON，字段：title, "
                "content（Markdown 格式，包含搜索关键词分类、内容平台分析、本地生活渠道、"
                "私域渠道、转化路径分析。区分曝光型、信任型、收藏型、转化型内容）。",
            ),
        ]

        for art_id, art_type, title, path, desc, system_prompt in artifacts_spec:
            await _emit(emitter, RunEvent(
                event_type="step_start", gate=gate, step=art_id, agent="Knowledge Mapper",
                message=f"正在生成：{title}（{desc}）",
            ))

            # Call LLM to generate content
            llm_result = await _llm_generate(
                llm_provider,
                system_prompt=system_prompt,
                user_prompt=(
                    f"行业：{project['domain']}\n"
                    f"市场范围：{project['market_scope']}\n"
                    f"研究深度：{project['depth']}\n"
                    f"已有证据数量：{len(state['evidence'])} 条\n"
                    f"研究框架：{', '.join(a.get('title', '') for a in state['artifacts'])}\n"
                    f"{'用户方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
                ),
                fallback={
                    "title": title,
                    "content": f"# {project['domain']} {title}\n\n需要配置 LLM 以生成详细内容。",
                },
                emitter=emitter, gate=gate, agent="Knowledge Mapper",
            )

            if isinstance(llm_result, dict):
                content = llm_result.get("content", f"# {title}\n\n内容生成中。")
                if not content.startswith("#"):
                    content = f"# {project['domain']} {title}\n\n{content}"
            else:
                content = f"# {project['domain']} {title}\n\n{llm_result}"

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
                message=f"{title}已生成（{len(content)} 字）",
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


def _make_opportunity_gate(llm_provider: LLMProvider | None, emitter: EventEmitter | None):
    async def opportunity_gate(state: dict[str, Any]) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.OPPORTUNITY.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate,
            message="正在分析机会地图",
        ))

        await _emit(emitter, RunEvent(
            event_type="step_start", gate=gate, step="opportunity", agent="Opportunity Analyst",
            message="正在基于行业数据识别机会假设...",
        ))

        # Summarize what we know for the LLM
        artifact_titles = [a.get("title", "") for a in state["artifacts"]]
        evidence_count = len(state["evidence"])

        llm_result = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是机会分析 Agent。基于前面的行业研究，为指定行业生成机会地图。"
                "只返回 JSON，字段：title, content（Markdown 格式，包含："
                "第一批机会假设列表，每个假设包含：机会名称、机会逻辑、目标用户、"
                "进入门槛、需要的资源、主要风险、第一周可以验证什么）。"
                "至少给出 3 个机会假设。"
            ),
            user_prompt=(
                f"行业：{project['domain']}\n"
                f"市场范围：{project['market_scope']}\n"
                f"已完成的研究：{', '.join(artifact_titles)}\n"
                f"证据数量：{evidence_count} 条\n"
                f"{'用户方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            fallback={
                "title": "机会地图",
                "content": (
                    f"# {project['domain']} 机会地图\n\n"
                    "## 第一批机会假设\n\n"
                    "- 找出用户痛点强但内容供给不足的细分主题。\n"
                    "- 找出信任成本高、但可用案例和证据降低风险的交易单位。\n"
                    "- 找出第一周可验证的问题：用户是否搜索、是否咨询、是否愿意付费。\n"
                ),
            },
            emitter=emitter, gate=gate, agent="Opportunity Analyst",
        )

        if isinstance(llm_result, dict):
            content = llm_result.get("content", "")
            if not content.startswith("#"):
                content = f"# {project['domain']} 机会地图\n\n{content}"
        else:
            content = f"# {project['domain']} 机会地图\n\n{llm_result}"

        artifact = Artifact(
            id="ART-OPPORTUNITY-MAP",
            project_id=state["project_id"],
            artifact_type=ArtifactType.OPPORTUNITY_MAP,
            title="机会地图",
            content_path="05-机会地图/opportunity-map.md",
            content=content,
            source_evidence_ids=_evidence_ids(state),
        )
        state["artifacts"].append(artifact.model_dump(mode="json"))

        await _emit(emitter, RunEvent(
            event_type="artifact_created", gate=gate, agent="Opportunity Analyst",
            message=f"机会地图已生成（{len(content)} 字）",
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
                message=f"质量门检查通过（{len(state['artifacts'])} 个产物，{len(state['evidence'])} 条证据）",
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
            message=f"已生成 {len(state['artifacts'])} 个产物，{len(state['evidence'])} 条证据",
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
