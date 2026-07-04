"""Agent registry, supervisor planning rules, and workflow definitions."""

from backend.app.schemas import (
    AgentRunMode,
    AgentSelectionDecision,
    AgentSelectionSignal,
    AgentTask,
    ResearchProject,
    SkippedAgent,
    SourcePolicy,
    SupervisorPlan,
    VerificationLevel,
    VerificationPlan,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeStatus,
)


def _source_scope(policy: SourcePolicy, include_brief: bool, include_user_materials: bool) -> list[str]:
    scope: list[str] = []
    if policy == SourcePolicy.OPEN_WEB:
        scope.append("open_web")
    if policy == SourcePolicy.RELIABLE_FIRST:
        scope.extend(["open_web", "government_sites", "company_disclosures", "public_databases"])
    if policy in (SourcePolicy.RELIABLE_FIRST, SourcePolicy.RELIABLE_ONLY):
        scope.extend(["reliable_sources", "government_sites", "company_disclosures", "public_databases"])
    if policy == SourcePolicy.USER_MATERIALS_ONLY or include_user_materials:
        scope.append("user_materials")
    if include_brief:
        scope.append("assistant_brief")
    if "project_rag" not in scope:
        scope.append("project_rag")
    return list(dict.fromkeys(scope))


def _build_selection_decision(
    *,
    agent_id: str,
    display_name: str,
    enabled: bool,
    score: int,
    source_scope: list[str],
    signals: list[AgentSelectionSignal],
    rationale: list[str],
    disqualifiers: list[str] | None = None,
) -> AgentSelectionDecision:
    return AgentSelectionDecision(
        agent_id=agent_id,
        display_name=display_name,
        enabled=enabled,
        score=score,
        source_scope=source_scope,
        signals=signals,
        rationale=rationale,
        disqualifiers=disqualifiers or [],
    )


def build_supervisor_plan(
    project: ResearchProject,
    user_guidance: str | None = None,
    has_assistant_brief: bool = False,
    has_user_materials: bool = False,
) -> SupervisorPlan:
    """Create a deterministic first-pass plan.

    The LLM can later enrich this plan, but this rule matrix keeps weaker
    models inside known-safe boundaries.
    """
    policy = project.source_policy
    text = f"{project.domain} {user_guidance or ''}".lower()
    content_keywords = ["自媒体", "内容", "账号", "流量", "获客", "转化", "教育", "本地生活", "消费"]
    risk_keywords = ["风险", "合规", "政策", "监管", "资质", "处罚", "医疗", "金融", "数据", "政府采购", "合作"]
    learning_keywords = ["学习", "了解", "框架", "工具", "方法"]
    venture_keywords = ["创业", "变现", "机会", "入局", "商业", "产品"]

    enable_content = any(word in text for word in content_keywords)
    enable_risk = policy in (SourcePolicy.RELIABLE_FIRST, SourcePolicy.RELIABLE_ONLY) or any(
        word in text for word in risk_keywords
    )
    learning_bias = any(word in text for word in learning_keywords)
    venture_bias = any(word in text for word in venture_keywords)

    source_scope = _source_scope(policy, has_assistant_brief, has_user_materials)
    degraded_for_learning = learning_bias and not venture_bias
    selection_trace: list[AgentSelectionDecision] = []

    selected: list[AgentTask] = [
        AgentTask(
            agent_id="search_scout",
            display_name="搜索侦察 Agent",
            role="生成查询并收集候选资料，不直接下最终结论。",
            reason="商业情报研究需要先建立候选资料池。",
            execution_group="source_intake",
            source_scope=source_scope,
            output_contract="source_candidates_v1",
            verification_level=VerificationLevel.NORMAL,
            fallback="搜索不可用时记录缺口，继续使用用户材料和系统范围证据。",
        ),
        AgentTask(
            agent_id="evidence_curator",
            display_name="证据整理 Agent",
            role="标准化证据、评级来源、识别需要反证的关键主张。",
            reason="所有后续分析必须基于证据账本，而不是自由文本。",
            execution_group="evidence",
            depends_on=["search_scout"],
            source_scope=source_scope,
            output_contract="evidence_ledger_v1",
            verification_level=VerificationLevel.STRICT,
            fallback="证据不足时输出待验证问题，阻止强结论进入导出。",
        ),
        AgentTask(
            agent_id="market_agent",
            display_name="市场分析 Agent",
            role="分析市场规模、增长驱动、限制因素和细分机会。",
            reason="商业情报主线默认需要市场基础数据库。",
            execution_group="business_database",
            depends_on=["evidence_curator"],
            source_scope=source_scope,
            output_contract="market_profile_v1",
            verification_level=VerificationLevel.STRICT,
            fallback="可靠数据不足时输出缺口，不生成确定性规模判断。",
        ),
        AgentTask(
            agent_id="player_agent",
            display_name="玩家分析 Agent",
            role="识别玩家类型、产业链角色、代表玩家和议价能力。",
            reason="理解行业如何分工和分钱需要玩家地图。",
            execution_group="business_database",
            depends_on=["evidence_curator"],
            source_scope=source_scope,
            output_contract="player_map_v1",
            verification_level=VerificationLevel.STRICT,
            fallback="玩家地位不足以确认时标记为待验证。",
        ),
        AgentTask(
            agent_id="transaction_agent",
            display_name="交易单位 Agent",
            role="拆解用户真正付费的交易单位、价格、频率、复购和风险。",
            reason="商业逻辑通常隐藏在交易单位中。",
            run_mode=AgentRunMode.DEGRADED if degraded_for_learning else AgentRunMode.REQUIRED,
            execution_group="business_database",
            depends_on=["evidence_curator"],
            source_scope=source_scope,
            output_contract="transaction_units_v1",
            verification_level=VerificationLevel.NORMAL,
            fallback="缺少价格或频率证据时只输出分类和待验证问题。",
        ),
        AgentTask(
            agent_id="opportunity_agent",
            display_name="机会分析 Agent",
            role="基于已建数据库生成机会假设、进入门槛和第一周验证动作。",
            reason="商业情报最终需要形成可验证机会，而不是只停留在信息堆叠。",
            run_mode=AgentRunMode.DEGRADED if degraded_for_learning else AgentRunMode.REQUIRED,
            execution_group="synthesis",
            depends_on=["market_agent", "player_agent", "transaction_agent"],
            source_scope=source_scope,
            output_contract="opportunity_hypotheses_v1",
            verification_level=VerificationLevel.ADVERSARIAL,
            fallback="证据不足时只输出假设，不输出确定性建议。",
        ),
        AgentTask(
            agent_id="knowledge_mapper",
            display_name="知识地图 Agent",
            role="把通过质检的信息组织成知识地图和 Obsidian 卡片。",
            reason="项目目标是沉淀可持续更新的行业认知系统。",
            execution_group="synthesis",
            depends_on=["market_agent", "player_agent", "transaction_agent"],
            source_scope=["project_rag"],
            output_contract="knowledge_map_v1",
            verification_level=VerificationLevel.NORMAL,
            fallback="缺少部分模块时输出缺口和待验证目录。",
        ),
    ]

    skipped: list[SkippedAgent] = []
    base_score = 100
    selection_trace.extend(
        [
            _build_selection_decision(
                agent_id="search_scout",
                display_name="搜索侦察 Agent",
                enabled=True,
                score=base_score,
                source_scope=source_scope,
                signals=[
                    AgentSelectionSignal(signal="commercial_default", matched=True, weight=50, reason="商业情报默认需要建立候选资料池。"),
                    AgentSelectionSignal(signal=f"source_policy:{policy.value}", matched=True, weight=30, reason="信源模式决定搜索范围和可信度边界。"),
                ],
                rationale=["先建立候选资料池，再进入证据整理和业务分析。"],
            ),
            _build_selection_decision(
                agent_id="evidence_curator",
                display_name="证据整理 Agent",
                enabled=True,
                score=base_score,
                source_scope=source_scope,
                signals=[
                    AgentSelectionSignal(signal="evidence_first", matched=True, weight=60, reason="所有下游结论必须挂证据。"),
                    AgentSelectionSignal(signal=f"source_policy:{policy.value}", matched=True, weight=20, reason="不同信源模式都需要统一证据账本。"),
                ],
                rationale=["证据账本是质量门的前置条件。"],
            ),
            _build_selection_decision(
                agent_id="market_agent",
                display_name="市场分析 Agent",
                enabled=True,
                score=92,
                source_scope=source_scope,
                signals=[
                    AgentSelectionSignal(signal="commercial_default", matched=True, weight=45, reason="商业情报默认需要市场视角。"),
                    AgentSelectionSignal(signal="learning_bias", matched=learning_bias, weight=10 if learning_bias else 0, reason="学习型任务也需要行业边界和市场概况。"),
                ],
                rationale=["市场规模、驱动和约束是后续机会假设的前提。"],
            ),
            _build_selection_decision(
                agent_id="player_agent",
                display_name="玩家分析 Agent",
                enabled=True,
                score=90,
                source_scope=source_scope,
                signals=[
                    AgentSelectionSignal(signal="commercial_default", matched=True, weight=45, reason="理解谁在行业里分工和分钱。"),
                    AgentSelectionSignal(signal="venture_bias", matched=venture_bias, weight=10 if venture_bias else 0, reason="创业/入局目标更依赖玩家格局。"),
                ],
                rationale=["玩家地图决定对标对象和价值链位置。"],
            ),
            _build_selection_decision(
                agent_id="transaction_agent",
                display_name="交易单位 Agent",
                enabled=True,
                score=82 if degraded_for_learning else 95,
                source_scope=source_scope,
                signals=[
                    AgentSelectionSignal(signal="commercial_default", matched=True, weight=35, reason="交易单位揭示真实付费逻辑。"),
                    AgentSelectionSignal(signal="learning_bias", matched=learning_bias, weight=-15 if learning_bias else 0, reason="纯学习导向可降级交易单位深度。"),
                    AgentSelectionSignal(signal="venture_bias", matched=venture_bias, weight=15 if venture_bias else 0, reason="创业/变现目标强化交易单位分析。"),
                ],
                rationale=["交易单位决定商业可行性。"],
            ),
            _build_selection_decision(
                agent_id="opportunity_agent",
                display_name="机会分析 Agent",
                enabled=True,
                score=84 if degraded_for_learning else 96,
                source_scope=source_scope,
                signals=[
                    AgentSelectionSignal(signal="venture_bias", matched=venture_bias, weight=25 if venture_bias else 0, reason="创业/变现目标强化机会假设输出。"),
                    AgentSelectionSignal(signal="learning_bias", matched=learning_bias, weight=-10 if learning_bias else 0, reason="学习型任务可以降级机会判断。"),
                    AgentSelectionSignal(signal="commercial_default", matched=True, weight=30, reason="商业研究最终需要形成可验证机会。"),
                ],
                rationale=["机会不是拍脑袋结论，必须由前面数据库支撑。"],
            ),
            _build_selection_decision(
                agent_id="knowledge_mapper",
                display_name="知识地图 Agent",
                enabled=True,
                score=88,
                source_scope=["project_rag"],
                signals=[
                    AgentSelectionSignal(signal="knowledge_base_goal", matched=True, weight=50, reason="项目目标是沉淀可更新知识库。"),
                ],
                rationale=["把研究结果组织成长期可复用的知识结构。"],
            ),
        ]
    )

    if has_assistant_brief:
        selected.insert(
            0,
            AgentTask(
                agent_id="assistant_brief_agent",
                display_name="外部报告线索 Agent",
                role="拆解外部 AI 调研报告中的 claims、leads 和可疑结论。",
                reason="用户上传了外部 AI 报告，可作为低可信线索帮助起步。",
                execution_group="source_intake",
                source_scope=["assistant_brief"],
                output_contract="assistant_brief_claims_v1",
                verification_level=VerificationLevel.ADVERSARIAL,
                fallback="无法拆解时保留原文材料，但不作为事实证据。",
            ),
        )
        selection_trace.append(
            _build_selection_decision(
                agent_id="assistant_brief_agent",
                display_name="外部报告线索 Agent",
                enabled=True,
                score=78,
                source_scope=["assistant_brief"],
                signals=[
                    AgentSelectionSignal(signal="assistant_brief_uploaded", matched=True, weight=40, reason="用户上传了外部 AI 报告。"),
                    AgentSelectionSignal(signal="low_trust_leads_only", matched=True, weight=20, reason="外部 AI 报告只能提供线索。"),
                ],
                rationale=["保留外部报告的启发价值，但不让它直接变成事实依据。"],
            )
        )
    else:
        skipped.append(SkippedAgent(agent_id="assistant_brief_agent", display_name="外部报告线索 Agent", reason="未上传外部 AI 报告。"))
        selection_trace.append(
            _build_selection_decision(
                agent_id="assistant_brief_agent",
                display_name="外部报告线索 Agent",
                enabled=False,
                score=0,
                source_scope=["assistant_brief"],
                signals=[AgentSelectionSignal(signal="assistant_brief_uploaded", matched=False, weight=0, reason="未上传外部 AI 报告。")],
                rationale=[],
                disqualifiers=["没有外部 AI 报告输入。"],
            )
        )

    if has_user_materials:
        selected.insert(
            0,
            AgentTask(
                agent_id="user_materials_agent",
                display_name="用户材料 Agent",
                role="整理用户粘贴的资料、笔记或链接，作为用户材料证据。",
                reason="用户提供了补充材料。",
                execution_group="source_intake",
                source_scope=["user_materials"],
                output_contract="user_materials_v1",
                verification_level=VerificationLevel.NORMAL,
                fallback="资料结构不清晰时转为待验证用户材料。",
            ),
        )
        selection_trace.append(
            _build_selection_decision(
                agent_id="user_materials_agent",
                display_name="用户材料 Agent",
                enabled=True,
                score=80,
                source_scope=["user_materials"],
                signals=[AgentSelectionSignal(signal="user_materials_uploaded", matched=True, weight=35, reason="用户提供了补充材料。")],
                rationale=["优先保留用户已有知识，但仍进入证据账本统一处理。"],
            )
        )
    else:
        skipped.append(SkippedAgent(agent_id="user_materials_agent", display_name="用户材料 Agent", reason="未上传用户材料。"))
        selection_trace.append(
            _build_selection_decision(
                agent_id="user_materials_agent",
                display_name="用户材料 Agent",
                enabled=False,
                score=0,
                source_scope=["user_materials"],
                signals=[AgentSelectionSignal(signal="user_materials_uploaded", matched=False, weight=0, reason="未上传用户材料。")],
                rationale=[],
                disqualifiers=["没有用户材料输入。"],
            )
        )

    if enable_content:
        selected.append(
            AgentTask(
                agent_id="content_channel_agent",
                display_name="内容渠道 Agent",
                role="分析内容生态、平台、选题、账号类型和转化路径。",
                reason="用户目标或领域特征涉及内容、流量、获客或转化。",
                run_mode=AgentRunMode.OPTIONAL,
                execution_group="business_database",
                depends_on=["evidence_curator"],
                source_scope=source_scope,
                output_contract="content_channel_map_v1",
                verification_level=VerificationLevel.NORMAL,
                fallback="平台数据不足时输出人工补料建议。",
            )
        )
        selection_trace.append(
            _build_selection_decision(
                agent_id="content_channel_agent",
                display_name="内容渠道 Agent",
                enabled=True,
                score=86,
                source_scope=source_scope,
                signals=[
                    AgentSelectionSignal(signal="content_keywords", matched=True, weight=40, reason="领域或目标中出现内容/流量/获客类关键词。"),
                ],
                rationale=["该研究与内容获客、流量或平台生态高度相关。"],
            )
        )
    else:
        skipped.append(SkippedAgent(agent_id="content_channel_agent", display_name="内容渠道 Agent", reason="当前研究目标未明显依赖内容获客。"))
        selection_trace.append(
            _build_selection_decision(
                agent_id="content_channel_agent",
                display_name="内容渠道 Agent",
                enabled=False,
                score=20,
                source_scope=source_scope,
                signals=[AgentSelectionSignal(signal="content_keywords", matched=False, weight=0, reason="未触发内容生态相关关键词。")],
                rationale=[],
                disqualifiers=["当前任务不明显依赖内容获客。"],
            )
        )

    if enable_risk:
        selected.append(
            AgentTask(
                agent_id="policy_risk_agent",
                display_name="政策风险 Agent",
                role="识别政策、监管、合规、资质和处罚相关风险边界。",
                reason="当前信源策略或领域关键词要求更强风险核对。",
                run_mode=AgentRunMode.OPTIONAL,
                execution_group="business_database",
                depends_on=["evidence_curator"],
                source_scope=[item for item in source_scope if item != "assistant_brief"],
                output_contract="policy_risk_scan_v1",
                verification_level=VerificationLevel.STRICT,
                fallback="没有可靠公开来源时只输出待验证风险清单。",
            )
        )
        selection_trace.append(
            _build_selection_decision(
                agent_id="policy_risk_agent",
                display_name="政策风险 Agent",
                enabled=True,
                score=89,
                source_scope=[item for item in source_scope if item != "assistant_brief"],
                signals=[
                    AgentSelectionSignal(signal="risk_keywords", matched=any(word in text for word in risk_keywords), weight=25 if any(word in text for word in risk_keywords) else 0, reason="出现合规/政策/风险类关键词。"),
                    AgentSelectionSignal(signal=f"source_policy:{policy.value}", matched=policy in (SourcePolicy.RELIABLE_FIRST, SourcePolicy.RELIABLE_ONLY), weight=30 if policy in (SourcePolicy.RELIABLE_FIRST, SourcePolicy.RELIABLE_ONLY) else 0, reason="可靠优先或严格可靠模式强化风险核对。"),
                ],
                rationale=["可靠信源制度下，需要补齐政策与风险边界。"],
            )
        )
    else:
        skipped.append(SkippedAgent(agent_id="policy_risk_agent", display_name="政策风险 Agent", reason="未发现强监管或合规触发条件。"))
        selection_trace.append(
            _build_selection_decision(
                agent_id="policy_risk_agent",
                display_name="政策风险 Agent",
                enabled=False,
                score=18,
                source_scope=[item for item in source_scope if item != "assistant_brief"],
                signals=[AgentSelectionSignal(signal="risk_keywords", matched=False, weight=0, reason="未触发强监管或风险关键词。")],
                rationale=[],
                disqualifiers=["当前任务不以风险/政策核对为核心。"],
            )
        )

    return SupervisorPlan(
        intent_summary=f"围绕「{project.domain}」建立商业情报知识库，兼顾领域认知、玩家结构、交易单位和机会假设。",
        source_policy=policy.value,
        source_policy_reason=_source_policy_reason(policy),
        selected_agents=selected,
        skipped_agents=skipped,
        verification_plan=VerificationPlan(
            key_claim_types=["market_size", "growth_trend", "player_status", "opportunity", "policy_risk"],
            counterevidence_triggers=[
                "外部 AI 报告提出但缺少可靠来源支撑的判断",
                "营销、社区、单一媒体来源支撑的关键判断",
                "头部玩家、市场规模、机会、风险等高影响结论",
            ],
            downgraded_source_types=["assistant_brief", "community", "media"],
            notes="弱来源只提供线索，不能单独支撑最终结论。",
        ),
        human_review_points=["确认本次研究计划、信源模式和可选 Agent 是否符合你的意图。"],
        success_criteria=[
            "生成证据账本并标注来源质量。",
            "完成市场、玩家、交易单位和机会假设的基础产物。",
            "关键低可信结论被标记为待验证或触发反证。",
            "导出产物引用 evidence_id。",
        ],
        assumptions=[
            "用户希望建立可继续更新的行业认知系统，而不是一次性报告。",
            "用户补充方向用于调整研究重点，具体资料查证仍由系统负责。",
        ],
        risks=[
            "开放网络可能混入营销或二手观点。",
            "可靠信源覆盖不足时，部分结论只能以待验证形式保留。",
        ],
        selection_trace=selection_trace,
    )


def _source_policy_reason(policy: SourcePolicy) -> str:
    if policy == SourcePolicy.OPEN_WEB:
        return "覆盖优先，适合探索型研究；所有关键结论仍需证据评级。"
    if policy == SourcePolicy.RELIABLE_ONLY:
        return "只使用可靠公开来源，适合严肃风险、政策或公告场景。"
    if policy == SourcePolicy.USER_MATERIALS_ONLY:
        return "仅处理用户材料，不主动开放搜索。"
    return "可靠来源优先，不足时使用开放网络补充，是商业情报的稳健默认策略。"


def build_v1_master_workflow_definition() -> WorkflowDefinition:
    """Workflow definition for the product-facing V1.6 Master Agent path."""

    nodes = [
        WorkflowNode(
            id="scope",
            label="定义领域边界",
            node_type="gate",
            group="scope",
            reason="明确研究对象、市场范围、信源策略和学习目标。",
        ),
        WorkflowNode(
            id="master_agent",
            label="主管节点 / ReAct",
            node_type="gate",
            agent_id="master_agent",
            group="plan",
            reason="理解任务、读取材料、规划工具调用，并决定继续、补搜、降级或中断。",
        ),
        WorkflowNode(
            id="external_report_intake",
            label="外部报告入库",
            node_type="agent",
            agent_id="external_report_agent",
            group="source",
            reason="读取上传报告、用户材料和引用链接，使其作为真实但低可信的研究输入进入证据账本。",
        ),
        WorkflowNode(
            id="source_collection",
            label="意图驱动搜索",
            node_type="agent",
            agent_id="search_scout",
            group="source",
            reason="由 Master Agent 生成多维搜索计划，按概念、趋势、政策、案例、需求等角度调用搜索工具。",
        ),
        WorkflowNode(
            id="evidence_ledger",
            label="证据账本",
            node_type="store",
            group="evidence",
            reason="去重、清洗摘要、保留来源链接、证据 ID 和待验证状态。",
        ),
        WorkflowNode(
            id="coverage_evaluation",
            label="覆盖充分性判断",
            node_type="gate",
            agent_id="master_agent",
            group="evidence",
            reason="按概念边界、现状、趋势、政策/风险、案例/玩家、用户需求和信源质量判断是否需要再搜。",
        ),
        WorkflowNode(
            id="knowledge_structuring",
            label="LLM 知识建库",
            node_type="group",
            agent_id="knowledge_builder",
            group="analysis",
            reason="在覆盖判断允许后，抽取概念、架构、工具、趋势、学习路径和待验证问题。",
        ),
        WorkflowNode(
            id="document_writing",
            label="逐文档写作",
            node_type="agent",
            agent_id="document_writer",
            group="synthesis",
            reason="让 LLM 分别写主文档，避免把搜索结果直接粘贴成模板。",
        ),
        WorkflowNode(
            id="artifact_review",
            label="详实度审查",
            node_type="gate",
            agent_id="artifact_reviewer",
            group="qa",
            reason="检查主文档是否过薄、缺例子、缺证据或缺 Obsidian 双向链接，并尽量扩写而不是删短。",
        ),
        WorkflowNode(
            id="export",
            label="Obsidian 导出 / RAG",
            node_type="agent",
            agent_id="export_writer",
            group="export",
            reason="写入主文档、知识卡片、证据账本，并支持项目问答。",
        ),
    ]
    edges = [
        WorkflowEdge(id="v1-e-scope-master", source="scope", target="master_agent", label="研究目标"),
        WorkflowEdge(id="v1-e-master-report", source="master_agent", target="external_report_intake", label="读取上传材料"),
        WorkflowEdge(id="v1-e-master-search", source="master_agent", target="source_collection", label="规划搜索工具"),
        WorkflowEdge(id="v1-e-report-ledger", source="external_report_intake", target="evidence_ledger", label="报告证据"),
        WorkflowEdge(id="v1-e-search-ledger", source="source_collection", target="evidence_ledger", label="搜索证据"),
        WorkflowEdge(id="v1-e-ledger-coverage", source="evidence_ledger", target="coverage_evaluation", label="覆盖检查"),
        WorkflowEdge(id="v1-e-coverage-loop", source="coverage_evaluation", target="master_agent", label="缺口补搜 / 降级决策"),
        WorkflowEdge(id="v1-e-coverage-knowledge", source="coverage_evaluation", target="knowledge_structuring", label="允许建库"),
        WorkflowEdge(id="v1-e-knowledge-writing", source="knowledge_structuring", target="document_writing"),
        WorkflowEdge(id="v1-e-writing-review", source="document_writing", target="artifact_review"),
        WorkflowEdge(id="v1-e-review-export", source="artifact_review", target="export"),
    ]
    return WorkflowDefinition(nodes=nodes, edges=edges)


def build_workflow_definition(plan: SupervisorPlan | None = None) -> WorkflowDefinition:
    nodes = [
        WorkflowNode(id="scope", label="范围确认", node_type="gate", group="scope"),
        WorkflowNode(id="supervisor_plan", label="主管计划", node_type="gate", group="plan"),
        WorkflowNode(id="human_confirm_plan", label="人工确认计划", node_type="human", group="plan"),
        WorkflowNode(id="source_strategy", label="信源策略", node_type="gate", group="source"),
        WorkflowNode(id="source_intake", label="信源接入", node_type="group", group="source"),
        WorkflowNode(id="claim_extractor", label="Claim 拆解", node_type="agent", agent_id="claim_extractor", group="evidence"),
        WorkflowNode(id="counterevidence", label="反证搜索", node_type="agent", agent_id="counterevidence_agent", group="evidence"),
        WorkflowNode(id="evidence_curator", label="证据整理", node_type="agent", agent_id="evidence_curator", group="evidence"),
        WorkflowNode(id="evidence_ledger", label="证据账本", node_type="store", group="evidence"),
        WorkflowNode(id="business_database", label="商业数据库", node_type="group", group="analysis"),
        WorkflowNode(id="synthesis", label="知识/机会综合", node_type="group", group="synthesis"),
        WorkflowNode(id="qa_critic", label="质量门", node_type="gate", agent_id="qa_critic", group="qa"),
        WorkflowNode(id="export", label="导出", node_type="agent", agent_id="export_writer", group="export"),
        WorkflowNode(id="rag_indexer", label="RAG 索引", node_type="agent", agent_id="rag_indexer", group="export"),
    ]
    edges = [
        WorkflowEdge(id="e-scope-plan", source="scope", target="supervisor_plan"),
        WorkflowEdge(id="e-plan-confirm", source="supervisor_plan", target="human_confirm_plan"),
        WorkflowEdge(id="e-confirm-source", source="human_confirm_plan", target="source_strategy"),
        WorkflowEdge(id="e-source-intake", source="source_strategy", target="source_intake"),
        WorkflowEdge(id="e-intake-claims", source="source_intake", target="claim_extractor"),
        WorkflowEdge(id="e-claims-curator", source="claim_extractor", target="evidence_curator"),
        WorkflowEdge(id="e-curator-counter", source="evidence_curator", target="counterevidence"),
        WorkflowEdge(id="e-counter-ledger", source="counterevidence", target="evidence_ledger"),
        WorkflowEdge(id="e-ledger-business", source="evidence_ledger", target="business_database"),
        WorkflowEdge(id="e-business-synthesis", source="business_database", target="synthesis"),
        WorkflowEdge(id="e-synthesis-qa", source="synthesis", target="qa_critic"),
        WorkflowEdge(id="e-qa-export", source="qa_critic", target="export"),
        WorkflowEdge(id="e-export-rag", source="export", target="rag_indexer"),
    ]

    if plan:
        enabled_agents = {task.agent_id: task for task in plan.selected_agents}
        for node in nodes:
            if node.agent_id in enabled_agents:
                task = enabled_agents[node.agent_id]
                node.status = WorkflowNodeStatus.ENABLED
                node.reason = task.reason
                node.details = task.model_dump(mode="json")

        source_children = [
            ("search_scout", "搜索侦察", "source_intake"),
            ("assistant_brief_agent", "外部报告线索", "source_intake"),
            ("user_materials_agent", "用户材料", "source_intake"),
        ]
        business_children = [
            ("market_agent", "市场分析", "business_database"),
            ("player_agent", "玩家分析", "business_database"),
            ("transaction_agent", "交易单位", "business_database"),
            ("content_channel_agent", "内容渠道", "business_database"),
            ("policy_risk_agent", "政策风险", "business_database"),
            ("opportunity_agent", "机会分析", "synthesis"),
            ("knowledge_mapper", "知识地图", "synthesis"),
        ]
        for group_id, label, source in [
            ("source_intake", "信源接入", "source_strategy"),
            ("business_database", "商业数据库", "evidence_ledger"),
            ("synthesis", "综合输出", "business_database"),
        ]:
            group_node = next((node for node in nodes if node.id == group_id), None)
            if group_node:
                group_node.status = WorkflowNodeStatus.ENABLED
                group_node.reason = f"{label} 承接上游阶段并汇聚子 Agent 输出。"
        for node in nodes:
            if node.id in {"claim_extractor", "counterevidence"}:
                node.reason = node.reason or "该节点用于显式暴露证据处理链路。"
        for agent_id, label, group in source_children + business_children:
            task = enabled_agents.get(agent_id)
            status = WorkflowNodeStatus.ENABLED if task else WorkflowNodeStatus.SKIPPED
            reason = task.reason if task else _skip_reason(plan, agent_id)
            nodes.append(
                WorkflowNode(
                    id=agent_id,
                    label=label,
                    node_type="agent",
                    agent_id=agent_id,
                    group=group,
                    status=status,
                    reason=reason,
                    details=task.model_dump(mode="json") if task else {},
                )
            )
            edges.append(WorkflowEdge(id=f"e-{group}-{agent_id}", source=group, target=agent_id))
        edges.extend(
            [
                WorkflowEdge(id="e-source-intake-claim", source="source_intake", target="claim_extractor"),
                WorkflowEdge(id="e-claim-counter", source="claim_extractor", target="counterevidence"),
                WorkflowEdge(id="e-counter-ledger-v2", source="counterevidence", target="evidence_ledger"),
                WorkflowEdge(id="e-business-qa", source="business_database", target="qa_critic"),
            ]
        )

    return WorkflowDefinition(nodes=nodes, edges=edges)


def _skip_reason(plan: SupervisorPlan, agent_id: str) -> str:
    for skipped in plan.skipped_agents:
        if skipped.agent_id == agent_id:
            return skipped.reason
    return "本次计划未启用。"
