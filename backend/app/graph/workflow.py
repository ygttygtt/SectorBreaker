"""Modern LangGraph workflow with typed state and explicit node/edge graph.

LangGraph 1.x pattern:
- TypedDict state schema
- Node functions return partial state updates
- add_node / add_edge / add_conditional_edges
"""

import asyncio
import json
import time
from typing import Any, Callable, Awaitable, TypedDict

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
    RunStatus,
    VerificationStatus,
)

# ── Types ──────────────────────────────────────────────────────

EventEmitter = Callable[[RunEvent], Awaitable[None]]


class WorkflowState(TypedDict, total=False):
    """Typed state for the LangGraph workflow."""
    project: dict[str, Any]
    project_id: str
    current_gate: str
    evidence: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    coverage_checklist: dict[str, bool]
    qa_issues: list[str]
    user_guidance: str | None
    user_evidence_items: list[dict[str, Any]]


# ── Constants ──────────────────────────────────────────────────

GATE_ORDER: list[str] = [
    ResearchGate.SCOPE.value,
    ResearchGate.EVIDENCE.value,
    ResearchGate.RESEARCH_FRAME.value,
    ResearchGate.KNOWLEDGE_MAP.value,
    ResearchGate.OPPORTUNITY.value,
    "qa_critic",
    ResearchGate.EXPORT.value,
]

HUMAN_REVIEW_GATES: set[str] = {
    ResearchGate.SCOPE.value,
    ResearchGate.RESEARCH_FRAME.value,
    ResearchGate.OPPORTUNITY.value,
}

_LLM_CONCURRENCY = 3
_llm_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)
    return _llm_semaphore


# ── Helpers ────────────────────────────────────────────────────

async def _emit(emitter: EventEmitter | None, event: RunEvent) -> None:
    if emitter is not None:
        await emitter(event)


async def _llm_generate(
    llm_provider: LLMProvider | None,
    system_prompt: str,
    user_prompt: str,
    emitter: EventEmitter | None,
    gate: str,
    agent: str,
    retries: int = 2,
) -> dict | str:
    if llm_provider is None:
        raise RuntimeError("LLM 未配置。请先在页面右下角点击「LLM 设置」配置 API 地址和密钥。")
    last_error = None
    for attempt in range(retries):
        try:
            return await llm_provider.complete_structured(
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_prompt),
                ],
                response_schema=dict,
            )
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                await _emit(emitter, RunEvent(
                    event_type="error", gate=gate, agent=agent,
                    message=f"LLM 调用失败（第 {attempt+1} 次），重试中... ({exc})",
                ))
                await asyncio.sleep(2)
    raise last_error


def _evidence_ids(state: WorkflowState) -> list[str]:
    return [item["id"] for item in state.get("evidence", [])]


def _extract_content(llm_result: dict | str, title: str, domain: str) -> str:
    """Extract content from LLM result, handling various response formats."""
    if isinstance(llm_result, dict):
        content = (
            llm_result.get("content")
            or llm_result.get("text")
            or llm_result.get("result")
        )
        if not content:
            content = json.dumps(llm_result, ensure_ascii=False, indent=2)
        if not str(content).startswith("#"):
            content = f"# {domain} {title}\n\n{content}"
        return str(content)
    return f"# {domain} {title}\n\n{llm_result}"


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


def next_gate(current: str) -> str | None:
    try:
        idx = GATE_ORDER.index(current)
        if idx + 1 < len(GATE_ORDER):
            return GATE_ORDER[idx + 1]
    except ValueError:
        pass
    return None


# ── Node functions (modern LangGraph pattern) ─────────────────
# Each node: receives state dict, returns partial state update dict


def make_nodes(
    llm_provider: LLMProvider | None = None,
    search_provider: SearchProvider | None = None,
    emitter: EventEmitter | None = None,
) -> dict[str, Callable]:
    """Create all node functions with dependencies bound via closure."""

    async def scope_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.SCOPE.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate,
            message=f"正在确认研究范围：{project['domain']}",
        ))

        # Inject user evidence
        evidence = list(state.get("evidence", []))
        for item in state.get("user_evidence_items", []):
            evidence.append(EvidenceItem(
                id=f"EV-USER-{item.get('id', 'SUPPLEMENT')}",
                project_id=state["project_id"],
                source_title=item.get("source_title", "用户补充信息"),
                snippet=item.get("snippet", ""),
                summary=item.get("summary"),
                confidence=item.get("confidence", 0.8),
                verification_status=VerificationStatus.UNVERIFIED,
            ).model_dump(mode="json"))

        evidence.append(EvidenceItem(
            id="EV-USER-SCOPE",
            project_id=state["project_id"],
            source_title="User project scope",
            snippet=f"User wants to research {project['domain']} with {project['market_scope']} scope.",
            summary="User-provided scope and intent.",
            confidence=1.0,
            verification_status=VerificationStatus.UNVERIFIED,
        ).model_dump(mode="json"))

        # LLM scope analysis
        await _emit(emitter, RunEvent(
            event_type="step_start", gate=gate, step="scope_analysis", agent="Research Planner",
            message="正在分析领域边界和研究范围...",
        ))

        scope_analysis = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是行业研究规划 Agent。用户想研究一个领域，你需要：\n"
                "1. 分析这个领域的边界和定义\n"
                "2. 列出研究该领域最应先搞清楚的 10 个关键问题，每个说明：为什么重要、应该去哪里找答案、"
                "常见误判是什么、如果只用1小时应该优先查到什么程度\n"
                "3. 列出常见数据口径问题：指标名称、常见统计口径、容易混淆的地方、"
                "适合回答什么问题、不适合回答什么问题、建议优先查证的数据来源\n"
                "只返回 JSON，字段：domain_definition, boundaries, common_confusions, "
                "key_questions（列表，每个含 question/importance/source/common_mistake/priority_1h）, "
                "data_caliber（列表，每个含 metric/caliber/confusion/suitable_for/not_suitable_for/recommended_source）。"
            ),
            user_prompt=(
                f"领域：{project['domain']}\n"
                f"市场范围：{project['market_scope']}\n"
                f"研究深度：{project['depth']}\n"
                f"{'用户补充：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            emitter=emitter, gate=gate, agent="Research Planner",
        )

        # Build scope artifact
        if isinstance(scope_analysis, dict):
            definition = scope_analysis.get("domain_definition", "") or ""
            boundaries = scope_analysis.get("boundaries", "") or ""
            confusions = scope_analysis.get("common_confusions", []) or []
            questions_md = ""
            for q in scope_analysis.get("key_questions", []):
                if isinstance(q, dict):
                    questions_md += (
                        f"### {q.get('question', '')}\n"
                        f"- **为什么重要**：{q.get('importance', '')}\n"
                        f"- **去哪找答案**：{q.get('source', '')}\n"
                        f"- **常见误判**：{q.get('common_mistake', '')}\n"
                        f"- **1小时优先级**：{q.get('priority_1h', '')}\n\n"
                    )
            caliber_md = ""
            for c in scope_analysis.get("data_caliber", []):
                if isinstance(c, dict):
                    caliber_md += (
                        f"| {c.get('metric', '')} | {c.get('caliber', '')} | "
                        f"{c.get('confusion', '')} | {c.get('suitable_for', '')} | "
                        f"{c.get('not_suitable_for', '')} | {c.get('recommended_source', '')} |\n"
                    )
            if definition or boundaries:
                content = (
                    f"# {project['domain']} 研究范围分析\n\n"
                    f"## 领域定义\n\n{definition}\n\n"
                    f"## 边界说明\n\n{boundaries}\n\n"
                    f"## 常见混淆点\n\n" + "\n".join(f"- {c}" for c in confusions) + "\n\n"
                    f"## 关键问题（10个）\n\n{questions_md}\n"
                    f"## 数据口径\n\n| 指标 | 统计口径 | 容易混淆 | 适合回答 | 不适合回答 | 建议数据来源 |\n"
                    f"|------|---------|---------|---------|-----------|------------|\n{caliber_md}\n"
                )
            else:
                content = f"# {project['domain']} 研究范围分析\n\n{json.dumps(scope_analysis, ensure_ascii=False, indent=2)}"
        else:
            content = f"# {project['domain']} 研究范围分析\n\n{scope_analysis}"

        artifacts = list(state.get("artifacts", []))
        artifacts.append(Artifact(
            id="ART-SCOPE-ANALYSIS", project_id=state["project_id"],
            artifact_type=ArtifactType.RESEARCH_FRAME, title="研究范围分析",
            content_path="00-研究范围/scope-analysis.md", content=content,
            source_evidence_ids=[item["id"] for item in evidence],
        ).model_dump(mode="json"))

        await _emit(emitter, RunEvent(
            event_type="artifact_created", gate=gate, agent="Research Planner",
            message=f"范围分析完成：{content[:80]}...",
        ))
        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate, message="研究范围已确认",
        ))

        return {
            "current_gate": ResearchGate.EVIDENCE.value,
            "evidence": evidence,
            "artifacts": artifacts,
            "coverage_checklist": {
                **state.get("coverage_checklist", {}),
                "scope_confirmed": True,
                "research_frame": False,
                "knowledge_map": False,
                "opportunity_map": False,
            },
        }

    async def evidence_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.EVIDENCE.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate, message="正在收集行业证据",
        ))

        evidence = list(state.get("evidence", []))
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
                try:
                    results = await search_provider.search(
                        SearchQuery(query=query_text, market_scope=project["market_scope"], max_results=5)
                    )
                    for index, result in enumerate(results, start=1):
                        evidence.append(EvidenceItem(
                            id=f"EV-SEARCH-{query_idx}-{index:03d}",
                            project_id=state["project_id"],
                            source_title=result.title, source_url=result.url, source_type="web",
                            snippet=result.snippet, summary=result.snippet,
                            confidence=0.65, verification_status=VerificationStatus.PARTIALLY_VERIFIED,
                        ).model_dump(mode="json"))
                        await _emit(emitter, RunEvent(
                            event_type="evidence_collected", gate=gate, agent="Search Scout",
                            message=f"找到：{result.title}",
                        ))
                except Exception as exc:
                    await _emit(emitter, RunEvent(
                        event_type="error", gate=gate, agent="Search Scout", message=f"搜索失败：{exc}",
                    ))
            else:
                await _emit(emitter, RunEvent(
                    event_type="step_complete", gate=gate, step=f"search_{query_idx}", agent="Search Scout",
                    message="未配置搜索提供商，跳过",
                ))

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate, message="证据收集完成",
        ))
        return {"current_gate": ResearchGate.RESEARCH_FRAME.value, "evidence": evidence}

    async def research_frame_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.RESEARCH_FRAME.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate, message="正在生成研究框架",
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
            emitter=emitter, gate=gate, agent="Research Planner",
        )

        if isinstance(plan, dict):
            sections = [item for item in (plan.get("sections") or plan.get("topics") or plan.get("研究板块") or []) if item]
            key_questions = [item for item in (plan.get("key_questions") or plan.get("questions") or plan.get("关键问题") or []) if item]
        else:
            default = _default_plan()
            sections = default["sections"]
            key_questions = default["key_questions"]

        if not sections:
            default = _default_plan()
            sections = default["sections"]
            key_questions = key_questions or default["key_questions"]

        body = (
            f"# {project['domain']} 研究框架\n\n## 先学什么\n\n"
            + "\n".join(f"- {s}" for s in sections)
            + "\n\n## 关键问题\n\n"
            + "\n".join(f"- {q}" for q in key_questions) + "\n"
        )

        artifacts = list(state.get("artifacts", []))
        artifacts.append(Artifact(
            id="ART-RESEARCH-FRAME", project_id=state["project_id"],
            artifact_type=ArtifactType.RESEARCH_FRAME, title="研究框架",
            content_path="00-研究框架/research-frame.md", content=body,
            source_evidence_ids=_evidence_ids(state),
        ).model_dump(mode="json"))

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate, message="研究框架生成完成",
        ))
        return {
            "current_gate": ResearchGate.KNOWLEDGE_MAP.value,
            "artifacts": artifacts,
            "coverage_checklist": {
                **state.get("coverage_checklist", {}),
                "research_frame": bool(sections and key_questions),
            },
        }

    async def knowledge_map_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.KNOWLEDGE_MAP.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate, message="正在构建知识地图",
        ))

        artifacts_spec = [
            ("ART-INDUSTRY-MAP", ArtifactType.INDUSTRY_MAP, "行业地图", "01-行业地图", "行业地图与产业链结构",
             "你是行业研究 Agent。为指定行业生成结构化知识地图。返回 JSON，字段：nodes（一级节点列表，每个含 name/type/definition/children/questions/misconceptions，type 可选 supply/demand/channel/risk）、learning_order（学习顺序）、misconceptions（新手常见误解至少5个）。每个一级节点下至少2个二级节点。"),
            ("ART-MARKET-OVERVIEW", ArtifactType.MARKET_OVERVIEW, "市场现状", "02-市场分析/00-市场总览.md", "市场规模、增长驱动与约束",
             "你是市场分析 Agent。为指定行业生成市场现状分析。返回 JSON，字段：title, content（Markdown，包含市场规模、增长速度、核心细分市场、供给规模、增长驱动、限制因素、数据来源可信度、区分事实/推测/观点）。"),
            ("ART-PLAYER-MAP", ArtifactType.PLAYER_MAP, "玩家与交易单位", "03-玩家与竞品/00-玩家总览.md", "玩家角色与交易单位",
             "你是竞品分析 Agent。按角色分类分析玩家：提供服务/拥有用户/拥有渠道/掌握资源/负责交付/监管/从交易赚钱。每类给代表玩家、商业价值、议价能力、新手忽略的地方。返回 JSON，字段：title, content（Markdown）。"),
            ("ART-CONTENT-CHANNELS", ArtifactType.CONTENT_CHANNELS, "内容与渠道", "04-内容生态/00-内容总览.md", "内容生态与转化路径",
             "你是内容生态分析 Agent。分析搜索关键词（6类）、内容平台（小红书/抖音/B站/公众号/知乎）、转化路径、6种内容分类（曝光/信任/收藏/转化/案例/专家IP）。返回 JSON，字段：title, content（Markdown）。"),
            ("ART-TRANSACTION-UNITS", ArtifactType.TRANSACTION_UNITS, "交易单位数据库", "02-市场分析/交易单位", "用户真正付钱购买的东西",
             "你是商业模式分析 Agent。返回 JSON，字段：units（数组，每个含 name/why_buy/price_range/frequency/repurchase_cycle/decision_cost/delivery_difficulty/risks/margin_source/selling_points/user_keywords）。至少列出5个交易单位。"),
            ("ART-COMPETITOR-ANALYSIS", ArtifactType.COMPETITOR_ANALYSIS, "竞品数据库", "03-玩家与竞品", "代表玩家商业结构拆解",
             "你是竞品分析 Agent。返回 JSON，字段：players（数组，每个含 name/role/positioning/target_users/products/pricing/channels/conversion/trust_assets/retention/content_strategy/differentiation/risks/learn/avoid）。选5-10个代表性玩家。"),
            ("ART-REVENUE-STRUCTURE", ArtifactType.REVENUE_STRUCTURE, "收入结构", "02-市场分析/00-收入结构.md", "引流/转化/利润/复购",
             "你是商业模式分析 Agent。将收入拆成4类（引流/转化/利润/复购），每类给：常见形式、用户心理、价格区间、渠道、话术、风险、案例。返回 JSON，字段：title, content（Markdown）。"),
            ("ART-TRUST-ASSETS", ArtifactType.TRUST_ASSETS, "信任资产", "04-内容生态/00-信任资产.md", "用户信任建立机制",
             "你是信任分析 Agent。分析：用户最担心什么、凭什么相信、哪些证据最有说服力、哪些是包装、哪些资质必须查、哪些案例推动成交、新进入者缺什么。返回 JSON，字段：title, content（Markdown）。"),
            ("ART-CONTENT-ACCOUNTS", ArtifactType.CONTENT_ACCOUNTS, "内容账号数据库", "04-内容生态/内容账号", "批量内容账号分析",
             "你是内容生态分析 Agent。返回 JSON，字段：platforms（数组，每个含 platform/accounts，accounts 含 name/followers/direction/conversion/learn）。覆盖小红书/抖音/B站/公众号/知乎。"),
            ("ART-CONTENT-TOPICS", ArtifactType.CONTENT_TOPICS, "高频选题分析", "04-内容生态/00-高频选题.md", "反复出现的选题和用户问题",
             "你是内容分析 Agent。分析：哪些选题反复出现、哪些问题被反复提问、哪些内容收藏率高、哪些接近成交、哪些标题结构有效、哪些争议点说明决策焦虑。返回 JSON，字段：title, content（Markdown）。"),
            ("ART-KNOWLEDGE-CARD-TEMPLATE", ArtifactType.EXPORT_MANIFEST, "知识卡片模板", "06-知识卡片模板.md", "Obsidian 知识卡片结构化模板",
             "你是知识管理 Agent。创建 Obsidian 知识卡片模板。返回 JSON，字段：title, content（Markdown，含示例卡片、卡片结构说明、frontmatter 格式、使用说明）。"),
        ]

        # Artifacts that produce structured cards (not single files)
        STRUCTURED_ARTIFACTS = {
            "ART-INDUSTRY-MAP", "ART-COMPETITOR-ANALYSIS",
            "ART-TRANSACTION-UNITS", "ART-CONTENT-ACCOUNTS",
        }

        async def _gen(spec):
            art_id, art_type, title, path, desc, sys_prompt = spec
            await _emit(emitter, RunEvent(
                event_type="step_start", gate=gate, step=art_id, agent="Knowledge Mapper",
                message=f"正在生成：{title}（{desc}）",
            ))
            try:
                async with _get_semaphore():
                    result = await _llm_generate(
                        llm_provider, system_prompt=sys_prompt,
                        user_prompt=(
                            f"行业：{project['domain']}\n市场范围：{project['market_scope']}\n"
                            f"研究深度：{project['depth']}\n证据数：{len(state.get('evidence', []))}\n"
                            f"已有产物：{', '.join(a.get('title', '') for a in state.get('artifacts', []))}\n"
                            f"{'用户方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
                        ),
                        emitter=emitter, gate=gate, agent="Knowledge Mapper",
                    )

                ev_ids = _evidence_ids(state)
                generated = []

                if art_id in STRUCTURED_ARTIFACTS and isinstance(result, dict):
                    # Generate multiple cards from structured data
                    from backend.app.exporters import cards as card_gen

                    if art_id == "ART-INDUSTRY-MAP":
                        card_map = card_gen.generate_industry_map_cards(
                            project['domain'], result, project['title'], ev_ids)
                        for card_name, card_content in card_map.items():
                            generated.append(Artifact(
                                id=f"{art_id}-{card_name}", project_id=state["project_id"],
                                artifact_type=art_type, title=f"行业地图/{card_name}",
                                content_path=f"{path}/{card_name}.md", content=card_content,
                                source_evidence_ids=ev_ids,
                            ))
                    elif art_id == "ART-COMPETITOR-ANALYSIS":
                        card_map = card_gen.generate_competitor_cards(
                            project['domain'], result, project['title'], ev_ids)
                        for card_name, card_content in card_map.items():
                            generated.append(Artifact(
                                id=f"{art_id}-{card_name}", project_id=state["project_id"],
                                artifact_type=art_type, title=f"竞品/{card_name}",
                                content_path=f"{path}/{card_name}.md", content=card_content,
                                source_evidence_ids=ev_ids,
                            ))
                    elif art_id == "ART-TRANSACTION-UNITS":
                        card_map = card_gen.generate_transaction_unit_cards(
                            project['domain'], result, project['title'], ev_ids)
                        for card_name, card_content in card_map.items():
                            generated.append(Artifact(
                                id=f"{art_id}-{card_name}", project_id=state["project_id"],
                                artifact_type=art_type, title=f"交易单位/{card_name}",
                                content_path=f"{path}/{card_name}.md", content=card_content,
                                source_evidence_ids=ev_ids,
                            ))
                    elif art_id == "ART-CONTENT-ACCOUNTS":
                        card_map = card_gen.generate_content_account_cards(
                            project['domain'], result, project['title'], ev_ids)
                        for card_name, card_content in card_map.items():
                            generated.append(Artifact(
                                id=f"{art_id}-{card_name}", project_id=state["project_id"],
                                artifact_type=art_type, title=f"内容账号/{card_name}",
                                content_path=f"{path}/{card_name}.md", content=card_content,
                                source_evidence_ids=ev_ids,
                            ))
                else:
                    # Single file artifact
                    content = _extract_content(result, title, project['domain'])
                    generated.append(Artifact(
                        id=art_id, project_id=state["project_id"], artifact_type=art_type,
                        title=title, content_path=path, content=content,
                        source_evidence_ids=ev_ids,
                    ))

                await _emit(emitter, RunEvent(
                    event_type="artifact_created", gate=gate, agent="Knowledge Mapper",
                    message=f"{title}已生成（{len(generated)} 个卡片）",
                ))
                return generated
            except Exception as exc:
                await _emit(emitter, RunEvent(
                    event_type="error", gate=gate, agent="Knowledge Mapper",
                    message=f"{title}生成失败：{exc}",
                ))
                return [Artifact(
                    id=art_id, project_id=state["project_id"], artifact_type=art_type,
                    title=title, content_path=path,
                    content=f"# {project['domain']} {title}\n\n生成失败，请稍后重试。",
                    source_evidence_ids=_evidence_ids(state),
                )]

        results = await asyncio.gather(*[_gen(s) for s in artifacts_spec])
        new_artifacts = list(state.get("artifacts", []))
        for art_list in results:
            if art_list:
                for art in art_list:
                    new_artifacts.append(art.model_dump(mode="json"))

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate, message="知识地图构建完成",
        ))
        return {
            "current_gate": ResearchGate.OPPORTUNITY.value,
            "artifacts": new_artifacts,
            "coverage_checklist": {
                **state.get("coverage_checklist", {}),
                "knowledge_map": True,
            },
        }

    async def opportunity_gate(state: WorkflowState) -> dict[str, Any]:
        project = state["project"]
        gate = ResearchGate.OPPORTUNITY.value

        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate, message="正在分析机会地图",
        ))

        artifact_titles = [a.get("title", "") for a in state.get("artifacts", [])]

        llm_result = await _llm_generate(
            llm_provider,
            system_prompt=(
                "你是机会分析 Agent。基于前面的行业研究，为指定行业生成机会地图。"
                "只返回 JSON，字段：title, content（Markdown，包含：行业整体判断（增长快/竞争激烈）、"
                "至少3个机会假设，每个含：机会名称、逻辑、目标用户、痛点强但供给不足的领域、"
                "信任成本高的领域、进入门槛、资源、风险、适合新人的领域、第一周可验证什么）。"
            ),
            user_prompt=(
                f"行业：{project['domain']}\n市场范围：{project['market_scope']}\n"
                f"已完成研究：{', '.join(artifact_titles)}\n"
                f"证据数：{len(state.get('evidence', []))}\n"
                f"{'用户方向：' + state.get('user_guidance', '') if state.get('user_guidance') else ''}"
            ),
            emitter=emitter, gate=gate, agent="Opportunity Analyst",
        )

        ev_ids = _evidence_ids(state)
        artifacts = list(state.get("artifacts", []))

        if isinstance(llm_result, dict) and "hypotheses" in llm_result:
            # Structured opportunity cards
            from backend.app.exporters import cards as card_gen
            card_map = card_gen.generate_opportunity_cards(
                project['domain'], llm_result, project['title'], ev_ids)
            for card_name, card_content in card_map.items():
                artifacts.append(Artifact(
                    id=f"ART-OPPORTUNITY-MAP-{card_name}", project_id=state["project_id"],
                    artifact_type=ArtifactType.OPPORTUNITY_MAP, title=f"机会/{card_name}",
                    content_path=f"05-机会与验证/{card_name}.md", content=card_content,
                    source_evidence_ids=ev_ids,
                ).model_dump(mode="json"))
        else:
            # Fallback to single file
            content = _extract_content(llm_result, "机会地图", project['domain'])
            artifacts.append(Artifact(
                id="ART-OPPORTUNITY-MAP", project_id=state["project_id"],
                artifact_type=ArtifactType.OPPORTUNITY_MAP, title="机会地图",
                content_path="05-机会与验证/00-机会总览.md", content=content,
                source_evidence_ids=ev_ids,
            ).model_dump(mode="json"))

        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate=gate, message="机会地图分析完成",
        ))
        return {
            "current_gate": "qa_critic",
            "artifacts": artifacts,
            "coverage_checklist": {
                **state.get("coverage_checklist", {}),
                "opportunity_map": True,
            },
        }

    async def qa_critic_gate(state: WorkflowState) -> dict[str, Any]:
        gate = "qa_critic"
        await _emit(emitter, RunEvent(
            event_type="gate_start", gate=gate, message="质量门检查中",
        ))

        checklist = state.get("coverage_checklist", {})
        required = ["scope_confirmed", "research_frame", "knowledge_map", "opportunity_map"]
        missing = [k for k in required if not checklist.get(k)]
        qa_issues = list(state.get("qa_issues", []))
        if missing:
            qa_issues.append(f"研究框架或关键产物 coverage 不完整: {', '.join(missing)}")

        unsupported = [a["id"] for a in state.get("artifacts", []) if not a.get("source_evidence_ids")]
        if unsupported:
            qa_issues.append(f"存在缺少证据引用的产物: {', '.join(unsupported)}")

        if qa_issues:
            await _emit(emitter, RunEvent(
                event_type="error", gate=gate, agent="QA Critic",
                message=f"质量门发现问题：{'; '.join(qa_issues)}",
            ))
        else:
            await _emit(emitter, RunEvent(
                event_type="gate_complete", gate=gate,
                message=f"质量门检查通过（{len(state.get('artifacts', []))} 个产物，{len(state.get('evidence', []))} 条证据）",
            ))

        # If QA passes, move to export; if blocked, stay at opportunity
        next_g = ResearchGate.EXPORT.value if not qa_issues else ResearchGate.OPPORTUNITY.value
        return {"current_gate": next_g, "qa_issues": qa_issues}

    async def export_gate(state: WorkflowState) -> dict[str, Any]:
        await _emit(emitter, RunEvent(
            event_type="gate_start", gate="export", message="正在导出知识库",
        ))
        await _emit(emitter, RunEvent(
            event_type="step_complete", gate="export", step="write", agent="Export Writer",
            message=f"已生成 {len(state.get('artifacts', []))} 个产物，{len(state.get('evidence', []))} 条证据",
        ))
        await _emit(emitter, RunEvent(
            event_type="gate_complete", gate="export", message="研究完成！",
        ))
        return {"current_gate": ResearchGate.EXPORT.value}

    return {
        "scope_gate": scope_gate,
        "evidence_gate": evidence_gate,
        "research_frame_gate": research_frame_gate,
        "knowledge_map_gate": knowledge_map_gate,
        "opportunity_gate": opportunity_gate,
        "qa_critic_gate": qa_critic_gate,
        "export_gate": export_gate,
    }


# ── Graph construction ────────────────────────────────────────

def _route_after_qa(state: WorkflowState) -> str:
    if state.get("qa_issues"):
        return "blocked"
    return "export_gate"


def build_graph(
    llm_provider: LLMProvider | None = None,
    search_provider: SearchProvider | None = None,
    emitter: EventEmitter | None = None,
):
    """Build the LangGraph StateGraph with typed state and explicit edges."""
    nodes = make_nodes(llm_provider, search_provider, emitter)

    graph = StateGraph(WorkflowState)

    # Add nodes
    graph.add_node("scope_gate", nodes["scope_gate"])
    graph.add_node("evidence_gate", nodes["evidence_gate"])
    graph.add_node("research_frame_gate", nodes["research_frame_gate"])
    graph.add_node("knowledge_map_gate", nodes["knowledge_map_gate"])
    graph.add_node("opportunity_gate", nodes["opportunity_gate"])
    graph.add_node("qa_critic_gate", nodes["qa_critic_gate"])
    graph.add_node("export_gate", nodes["export_gate"])

    # Set entry point
    graph.set_entry_point("scope_gate")

    # Add edges
    graph.add_edge("scope_gate", "evidence_gate")
    graph.add_edge("evidence_gate", "research_frame_gate")
    graph.add_edge("research_frame_gate", "knowledge_map_gate")
    graph.add_edge("knowledge_map_gate", "opportunity_gate")
    graph.add_edge("opportunity_gate", "qa_critic_gate")

    # Conditional edge after QA
    graph.add_conditional_edges(
        "qa_critic_gate",
        _route_after_qa,
        {"export_gate": "export_gate", "blocked": END},
    )

    graph.add_edge("export_gate", END)

    return graph.compile()


# ── Public API ─────────────────────────────────────────────────


def _initial_state(project: ResearchProject) -> WorkflowState:
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


def _state_to_json(state: WorkflowState) -> str:
    return json.dumps(state, ensure_ascii=False, default=str)


def _state_from_json(data: str) -> WorkflowState:
    return json.loads(data)


def _to_research_state(raw: WorkflowState) -> ResearchState:
    return ResearchState(
        project_id=raw["project_id"],
        current_gate=ResearchGate(raw.get("current_gate", ResearchGate.EXPORT.value)),
        evidence=[EvidenceItem(**item) for item in raw.get("evidence", [])],
        artifacts=[Artifact(**item) for item in raw.get("artifacts", [])],
        coverage_checklist=raw.get("coverage_checklist", {}),
        qa_issues=raw.get("qa_issues", []),
    )


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

    graph = build_graph(llm_provider, search_provider, emitter)
    raw_state = await graph.ainvoke(state)

    return _to_research_state(raw_state)


async def run_workflow_until_pause(
    project: ResearchProject,
    search_provider: SearchProvider | None = None,
    llm_provider: LLMProvider | None = None,
    emitter: EventEmitter | None = None,
    state: WorkflowState | None = None,
    user_guidance: str | None = None,
    user_evidence_items: list[dict[str, Any]] | None = None,
    auto_run: bool = False,
) -> tuple[WorkflowState, str | None, bool]:
    """Run gates sequentially until one requires human review or all complete.

    Returns (state, paused_gate, completed).
    """
    if state is None:
        state = _initial_state(project)
    if user_guidance:
        state["user_guidance"] = user_guidance
    if user_evidence_items:
        state["user_evidence_items"] = user_evidence_items

    nodes = make_nodes(llm_provider, search_provider, emitter)
    current = state.get("current_gate", GATE_ORDER[0])

    while current:
        fn = nodes.get(current) or nodes.get(f"{current}_gate")
        if fn:
            update = await fn(state)
            state.update(update)
            state["current_gate"] = current

        # QA blocks further gates
        if current == "qa_critic" and state.get("qa_issues"):
            state["current_gate"] = ResearchGate.OPPORTUNITY.value
            return state, None, True

        # Check pause
        if not auto_run and current in HUMAN_REVIEW_GATES:
            nxt = next_gate(current)
            state["current_gate"] = nxt or current
            return state, current, False

        # Next gate
        nxt = next_gate(current)
        if nxt:
            state["current_gate"] = nxt
            current = nxt
        else:
            return state, None, True

    return state, None, True
