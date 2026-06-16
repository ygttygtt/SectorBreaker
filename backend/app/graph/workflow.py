"""Async adaptive research workflow with pause/resume support.

Gates are executed sequentially. After each gate, the workflow checks
if human review is required. If so, it pauses and returns a
WAITING_FOR_HUMAN status. The caller can then resume with user inputs.

For backward compatibility, `run_research_workflow` runs all gates
without pausing (used in tests).
"""

import asyncio
import json
from typing import Any, Callable, Awaitable

from backend.app.providers.interfaces import ChatMessage, LLMProvider, SearchProvider, SearchQuery
from backend.app.schemas import (
    Artifact,
    ArtifactType,
    EvidenceItem,
    ResearchGate,
    ResearchProject,
    ResearchState,
    RunEvent,
    RunStatus,
    VerificationStatus,
)

# Type alias for the event emitter callback
EventEmitter = Callable[[RunEvent], Awaitable[None]]

# Gate execution order
GATE_ORDER: list[str] = [
    ResearchGate.SCOPE.value,
    ResearchGate.EVIDENCE.value,
    ResearchGate.RESEARCH_FRAME.value,
    ResearchGate.KNOWLEDGE_MAP.value,
    ResearchGate.OPPORTUNITY.value,
    "qa_critic",
    ResearchGate.EXPORT.value,
]

# Gates that require human review before proceeding
HUMAN_REVIEW_GATES: set[str] = {
    ResearchGate.SCOPE.value,
    ResearchGate.RESEARCH_FRAME.value,
    ResearchGate.OPPORTUNITY.value,
}


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


# ── Workflow state management ────────────────────────────────────


def _initial_state(project: ResearchProject) -> dict[str, Any]:
    return {
        "project": project.model_dump(mode="json"),
        "project_id": project.id,
        "current_gate": ResearchGate.SCOPE.value,
        "evidence": [],
        "artifacts": [],
        "coverage_checklist": {},
        "qa_issues": [],
        "user_guidance": None,
        "user_evidence_items": [],
    }


def _state_to_json(state: dict[str, Any]) -> str:
    """Serialize workflow state for persistence."""
    return json.dumps(state, ensure_ascii=False, default=str)


def _state_from_json(data: str) -> dict[str, Any]:
    """Deserialize workflow state."""
    return json.loads(data)


def _gate_fn(gate_name: str):
    """Map gate name to its implementation function."""
    mapping = {
        ResearchGate.SCOPE.value: _run_scope_gate,
        ResearchGate.EVIDENCE.value: _run_evidence_gate,
        ResearchGate.RESEARCH_FRAME.value: _run_research_frame_gate,
        ResearchGate.KNOWLEDGE_MAP.value: _run_knowledge_map_gate,
        ResearchGate.OPPORTUNITY.value: _run_opportunity_gate,
        "qa_critic": _run_qa_critic_gate,
        ResearchGate.EXPORT.value: _run_export_gate,
    }
    return mapping.get(gate_name)


def next_gate(current: str) -> str | None:
    """Return the next gate name, or None if at the end."""
    try:
        idx = GATE_ORDER.index(current)
        if idx + 1 < len(GATE_ORDER):
            return GATE_ORDER[idx + 1]
    except ValueError:
        pass
    return None


# ── Public API ──────────────────────────────────────────────────


async def run_research_workflow(
    project: ResearchProject,
    search_provider: SearchProvider | None = None,
    llm_provider: LLMProvider | None = None,
    emitter: EventEmitter | None = None,
    user_guidance: str | None = None,
    user_evidence_items: list[dict[str, Any]] | None = None,
) -> ResearchState:
    """Run all gates without pausing (for tests and auto-run mode)."""
    state = _initial_state(project)
    state["user_guidance"] = user_guidance
    state["user_evidence_items"] = user_evidence_items or []

    for gate_name in GATE_ORDER:
        fn = _gate_fn(gate_name)
        if fn:
            state = await fn(state, search_provider, llm_provider, emitter)
            state["current_gate"] = gate_name

        # QA critic blocks further gates if issues found
        if gate_name == "qa_critic" and state.get("qa_issues"):
            state["current_gate"] = ResearchGate.OPPORTUNITY.value
            break

    return _to_research_state(state)


async def run_workflow_step(
    project: ResearchProject,
    gate_name: str,
    search_provider: SearchProvider | None = None,
    llm_provider: LLMProvider | None = None,
    emitter: EventEmitter | None = None,
    state: dict[str, Any] | None = None,
    user_guidance: str | None = None,
    user_evidence_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a single gate and return the updated state.

    Call this for each gate. After the call, check if the gate
    requires human review and whether to pause or continue.
    """
    if state is None:
        state = _initial_state(project)

    if user_guidance:
        state["user_guidance"] = user_guidance
    if user_evidence_items:
        state["user_evidence_items"] = user_evidence_items

    fn = _gate_fn(gate_name)
    if fn:
        state = await fn(state, search_provider, llm_provider, emitter)

    return state


async def run_workflow_until_pause(
    project: ResearchProject,
    search_provider: SearchProvider | None = None,
    llm_provider: LLMProvider | None = None,
    emitter: EventEmitter | None = None,
    state: dict[str, Any] | None = None,
    user_guidance: str | None = None,
    user_evidence_items: list[dict[str, Any]] | None = None,
    auto_run: bool = False,
) -> tuple[dict[str, Any], str | None, bool]:
    """Run gates until one requires human review or all gates complete.

    Returns (state, paused_gate, completed).
    - paused_gate: the gate that needs human review, or None
    - completed: True if all gates finished
    """
    if state is None:
        state = _initial_state(project)

    if user_guidance:
        state["user_guidance"] = user_guidance
    if user_evidence_items:
        state["user_evidence_items"] = user_evidence_items

    current = state.get("current_gate", GATE_ORDER[0])

    while current:
        fn = _gate_fn(current)
        if fn:
            state = await fn(state, search_provider, llm_provider, emitter)

        # QA critic blocks further gates if issues found
        if current == "qa_critic" and state.get("qa_issues"):
            state["current_gate"] = ResearchGate.OPPORTUNITY.value
            return state, None, True  # Treat as completed (blocked)

        # Check if this gate requires human review
        if not auto_run and current in HUMAN_REVIEW_GATES:
            nxt = next_gate(current)
            state["current_gate"] = nxt or current
            return state, current, False

        # Move to next gate
        nxt = next_gate(current)
        if nxt:
            state["current_gate"] = nxt
            current = nxt
        else:
            state["current_gate"] = current
            return state, None, True

    return state, None, True


def _to_research_state(raw: dict[str, Any]) -> ResearchState:
    return ResearchState(
        project_id=raw["project_id"],
        current_gate=ResearchGate(raw.get("current_gate", ResearchGate.EXPORT.value)),
        evidence=[EvidenceItem(**item) for item in raw["evidence"]],
        artifacts=[Artifact(**item) for item in raw["artifacts"]],
        coverage_checklist=raw.get("coverage_checklist", {}),
        qa_issues=raw.get("qa_issues", []),
    )


# ── Gate implementations ────────────────────────────────────────


async def _run_scope_gate(
    state: dict[str, Any],
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    emitter: EventEmitter | None,
) -> dict[str, Any]:
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

    # Use LLM to analyze domain scope
    await _emit(emitter, RunEvent(
        event_type="step_start", gate=gate, step="scope_analysis", agent="Research Planner",
        message="正在分析领域边界和研究范围...",
    ))

    scope_analysis = await _llm_generate(
        llm_provider,
        system_prompt=(
            "你是行业研究规划 Agent。用户想研究一个领域，你需要分析这个领域的边界。"
            "只返回 JSON，字段：domain_definition（领域定义）, boundaries（边界说明）, "
            "common_confusions（常见混淆点列表）, data_caliber（常见数据口径问题）, "
            "recommended_scope（建议研究范围）。"
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
            "data_caliber": "需区分市场规模、用户规模、供给规模等不同口径",
            "recommended_scope": "先从行业概况和主要玩家开始",
        },
        emitter=emitter, gate=gate, agent="Research Planner",
    )

    if isinstance(scope_analysis, dict):
        summary = scope_analysis.get("domain_definition", project['domain'])
        boundaries = scope_analysis.get("boundaries", "")
        confusions = scope_analysis.get("common_confusions", [])
        caliber = scope_analysis.get("data_caliber", "")
        scope_content = (
            f"{summary}。边界：{boundaries}。"
            f"常见混淆：{', '.join(str(c) for c in confusions)}。"
            f"数据口径：{caliber}"
        )
    else:
        scope_content = str(scope_analysis)

    await _emit(emitter, RunEvent(
        event_type="artifact_created", gate=gate, agent="Research Planner",
        message=f"范围分析完成：{scope_content[:80]}...",
    ))

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


async def _run_evidence_gate(
    state: dict[str, Any],
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    emitter: EventEmitter | None,
) -> dict[str, Any]:
    project = state["project"]
    gate = ResearchGate.EVIDENCE.value

    await _emit(emitter, RunEvent(
        event_type="gate_start", gate=gate,
        message="正在收集行业证据",
    ))

    search_queries = [
        f"{project['domain']} 行业概况 市场规模 趋势",
        f"{project['domain']} 主要玩家 竞争格局",
        f"{project['domain']} 用户痛点 机会",
    ]

    for query_idx, query_text in enumerate(search_queries):
        await _emit(emitter, RunEvent(
            event_type="step_start", gate=gate, step=f"search_{query_idx}", agent="Search Scout",
            message=f"正在搜索：{query_text}",
        ))

        if search_provider is not None:
            query = SearchQuery(query=query_text, market_scope=project["market_scope"], max_results=5)
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
                        event_type="evidence_collected", gate=gate, agent="Search Scout",
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
                event_type="step_complete", gate=gate, step=f"search_{query_idx}", agent="Search Scout",
                message="未配置搜索提供商，跳过",
            ))

    await _emit(emitter, RunEvent(
        event_type="step_complete", gate=gate, step="search",
        message=f"证据收集完成，共 {len(state['evidence'])} 条",
    ))
    await _emit(emitter, RunEvent(
        event_type="gate_complete", gate=gate,
        message="证据收集完成",
    ))
    return state


async def _run_research_frame_gate(
    state: dict[str, Any],
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    emitter: EventEmitter | None,
) -> dict[str, Any]:
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
    body = f"# {project['domain']} 研究框架\n\n## 先学什么\n\n{section_body}\n\n## 关键问题\n\n{question_body}\n"

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

    await _emit(emitter, RunEvent(
        event_type="gate_complete", gate=gate,
        message="研究框架生成完成",
    ))
    return state


async def _run_knowledge_map_gate(
    state: dict[str, Any],
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    emitter: EventEmitter | None,
) -> dict[str, Any]:
    project = state["project"]
    gate = ResearchGate.KNOWLEDGE_MAP.value

    await _emit(emitter, RunEvent(
        event_type="gate_start", gate=gate,
        message="正在构建知识地图",
    ))

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
            "同时识别主要交易单位（用户真正付钱购买的东西，包含客单价、购买频率、复购周期）。",
        ),
        (
            "ART-CONTENT-CHANNELS", ArtifactType.CONTENT_CHANNELS, "内容与渠道",
            "04-内容与渠道/content-channels.md",
            "内容生态、获客渠道与转化路径",
            "你是内容生态分析 Agent。为指定行业生成内容与渠道分析。只返回 JSON，字段：title, "
            "content（Markdown 格式，包含搜索关键词分类（信息型/比较型/风险型/价格型/本地型/购买意图型）、"
            "内容平台分析（小红书/抖音/B站/公众号/知乎/大众点评）、本地生活渠道、私域渠道、"
            "转化路径分析（从内容到成交的完整路径）。"
            "区分曝光型、信任型、收藏型、转化型、案例型、专家IP型内容，每类给出典型标题和用户行为）。",
        ),
        (
            "ART-COMPETITOR-ANALYSIS", ArtifactType.COMPETITOR_ANALYSIS, "竞品数据库",
            "05-竞品数据库/competitor-analysis.md",
            "代表玩家商业结构逐一拆解",
            "你是竞品分析 Agent。为指定行业的代表性玩家逐一分析商业结构。只返回 JSON，字段：title, "
            "content（Markdown 格式，选择 5-10 个代表性玩家，每个玩家分析：定位、目标用户、主推产品、"
            "价格结构、获客渠道、转化路径、信任资产、复购机制、内容策略、差异化优势、潜在风险、"
            "应该学习什么、不应该照搬什么）。",
        ),
        (
            "ART-REVENUE-STRUCTURE", ArtifactType.REVENUE_STRUCTURE, "收入结构",
            "06-收入结构/revenue-structure.md",
            "引流/转化/利润/复购产品拆解",
            "你是商业模式分析 Agent。为指定行业拆解收入结构。只返回 JSON，字段：title, "
            "content（Markdown 格式，将收入拆成 4 类：引流产品（让用户第一次进来）、"
            "转化产品（完成第一次付费）、利润产品（贡献主要毛利）、复购产品（长期现金流）。"
            "每类输出：常见形式、用户心理、价格区间、对应渠道、常见话术、常见风险、代表案例）。",
        ),
        (
            "ART-TRUST-ASSETS", ArtifactType.TRUST_ASSETS, "信任资产",
            "07-信任资产/trust-assets.md",
            "用户信任建立机制分析",
            "你是信任分析 Agent。为指定行业分析信任资产。只返回 JSON，字段：title, "
            "content（Markdown 格式，分析：用户最担心什么、用户凭什么相信一个玩家、"
            "哪些证据最有说服力、哪些证据只是营销包装、哪些资质或认证必须查证、"
            "哪些案例最能推动成交、新进入者最缺哪类信任资产）。",
        ),
    ]

    for art_id, art_type, title, path, desc, system_prompt in artifacts_spec:
        await _emit(emitter, RunEvent(
            event_type="step_start", gate=gate, step=art_id, agent="Knowledge Mapper",
            message=f"正在生成：{title}（{desc}）",
        ))

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
            fallback={"title": title, "content": f"# {project['domain']} {title}\n\n需要配置 LLM 以生成详细内容。"},
            emitter=emitter, gate=gate, agent="Knowledge Mapper",
        )

        if isinstance(llm_result, dict):
            content = llm_result.get("content", f"# {title}\n\n内容生成中。")
            if not content.startswith("#"):
                content = f"# {project['domain']} {title}\n\n{content}"
        else:
            content = f"# {project['domain']} {title}\n\n{llm_result}"

        artifact = Artifact(
            id=art_id, project_id=state["project_id"], artifact_type=art_type,
            title=title, content_path=path, content=content,
            source_evidence_ids=_evidence_ids(state),
        )
        state["artifacts"].append(artifact.model_dump(mode="json"))

        await _emit(emitter, RunEvent(
            event_type="artifact_created", gate=gate, agent="Knowledge Mapper",
            message=f"{title}已生成（{len(content)} 字）",
            data={"artifact_id": art_id},
        ))

    state["coverage_checklist"]["knowledge_map"] = True

    await _emit(emitter, RunEvent(
        event_type="gate_complete", gate=gate,
        message="知识地图构建完成",
    ))
    return state


async def _run_opportunity_gate(
    state: dict[str, Any],
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    emitter: EventEmitter | None,
) -> dict[str, Any]:
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

    artifact_titles = [a.get("title", "") for a in state["artifacts"]]

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
            f"证据数量：{len(state['evidence'])} 条\n"
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

    await _emit(emitter, RunEvent(
        event_type="gate_complete", gate=gate,
        message="机会地图分析完成",
    ))
    return state


async def _run_qa_critic_gate(
    state: dict[str, Any],
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    emitter: EventEmitter | None,
) -> dict[str, Any]:
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


async def _run_export_gate(
    state: dict[str, Any],
    search_provider: SearchProvider | None,
    llm_provider: LLMProvider | None,
    emitter: EventEmitter | None,
) -> dict[str, Any]:
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


# ── Helpers ───────────────────────────────────────────────────────


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
