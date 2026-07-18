"""Legacy-compatible specialist planning helpers for V3 knowledge layers."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.agent_state.models import KnowledgeLayerId


class LayerSpecialistSpec(BaseModel):
    agent_id: str
    layer_id: KnowledgeLayerId
    name: str
    mission: str
    allowed_tools: list[str] = Field(default_factory=list)
    required_outputs: list[str] = Field(default_factory=list)
    completion_questions: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)

    def system_brief(self) -> str:
        return (
            f"你是 {self.name}，负责 {self.layer_id.value}。\n"
            f"任务：{self.mission}\n"
            f"可用工具：{', '.join(self.allowed_tools)}\n"
            f"必须输出：{', '.join(self.required_outputs)}\n"
            f"完成判断：{'；'.join(self.completion_questions)}\n"
            f"安全边界：{'；'.join(self.safety_notes) or '遵守项目证据和安全规则。'}"
        )


class FollowUpTask(BaseModel):
    task_id: str
    layer_id: KnowledgeLayerId
    title: str
    reason: str
    suggested_queries: list[str] = Field(default_factory=list)


class SpecialistTaskPlanner:
    """Create follow-up tasks when a specialist discovers important unknowns."""

    def discover_follow_up_tasks(
        self,
        *,
        domain: str,
        layer_id: KnowledgeLayerId,
        observations: list[str],
    ) -> list[FollowUpTask]:
        tasks: list[FollowUpTask] = []
        for term in self._important_terms(observations):
            tasks.append(FollowUpTask(
                task_id=f"follow-{layer_id.value}-{term}",
                layer_id=layer_id,
                title=f"继续下钻：{term}",
                reason=f"当前观察中出现“{term}”，它可能是理解 {domain} 的关键黑话、工具、资源或前置概念。",
                suggested_queries=[
                    f"{domain} {term} 是什么 原理",
                    f"{domain} {term} 流程 风险",
                    f"{domain} {term} 案例 防坑",
                ],
            ))
        return tasks[:8]

    @staticmethod
    def _important_terms(observations: list[str]) -> list[str]:
        markers = (
            "号池",
            "接码",
            "指纹浏览器",
            "代理IP",
            "注册机",
            "回测",
            "滑点",
            "保录取",
            "背景提升",
            "New-API",
            "One API",
            "RAG",
            "Agent",
        )
        text = "\n".join(observations)
        found = [marker for marker in markers if marker.lower() in text.lower()]
        return list(dict.fromkeys(found))


def default_specialist_specs() -> list[LayerSpecialistSpec]:
    return [
        LayerSpecialistSpec(
            agent_id="l1_concept_agent",
            layer_id=KnowledgeLayerId.WHAT_WHY,
            name="L1 本源与需求 Agent",
            mission="解释领域是什么、为什么存在、解决谁的什么痛点，并发现用户理解所需的前置概念。",
            allowed_tools=["search", "retrieve_project_memory", "read_uploaded_report"],
            required_outputs=["concept_entities", "what_why_claims", "prerequisite_questions", "evidence_ids"],
            completion_questions=["是否能用小白语言解释领域边界？", "是否说明了需求产生原因？", "是否发现了前置扫盲缺口？"],
        ),
        LayerSpecialistSpec(
            agent_id="l2_player_agent",
            layer_id=KnowledgeLayerId.WHO,
            name="L2 角色与玩家 Agent",
            mission="识别用户、供给方、主流玩家、关键资源持有者、社区和影响者。",
            allowed_tools=["search", "retrieve_project_memory", "source_verify"],
            required_outputs=["player_entities", "role_relationships", "user_segments", "evidence_ids"],
            completion_questions=["是否知道谁在用？", "是否知道谁在提供？", "是否有主流玩家和资源角色？"],
        ),
        LayerSpecialistSpec(
            agent_id="l3_how_agent",
            layer_id=KnowledgeLayerId.HOW,
            name="L3 原理与实操 Agent",
            mission="递归拆解实现原理、工具、流程、准备工作、隐藏术语和可学习路径。",
            allowed_tools=["search", "deep_read", "retrieve_project_memory"],
            required_outputs=["process_entities", "tool_entities", "implementation_claims", "follow_up_tasks", "evidence_ids"],
            completion_questions=["是否解释了基本实现路径？", "发现黑话时是否继续下钻？", "是否保留了未知术语和后续任务？"],
        ),
        LayerSpecialistSpec(
            agent_id="l4_incentive_agent",
            layer_id=KnowledgeLayerId.MONEY,
            name="L4 商业与激励 Agent",
            mission="拆解价值流、成本结构、盈利模式、上下游、外包环节和供需激励。",
            allowed_tools=["search", "retrieve_project_memory", "source_verify"],
            required_outputs=["incentive_claims", "supply_chain_relationships", "pricing_or_cost_signals", "evidence_ids"],
            completion_questions=["是否形成需求-服务-付费闭环？", "是否说明成本和上游？", "是否标记了不确定财务信息？"],
        ),
        LayerSpecialistSpec(
            agent_id="l5_risk_agent",
            layer_id=KnowledgeLayerId.RISKS,
            name="L5 风险与边界 Agent",
            mission="识别政策、平台、技术、伦理、安全、骗局和稳定性边界，并输出风险理解而非操作指南。",
            allowed_tools=["search", "source_verify", "risk_surface_scan"],
            required_outputs=["risk_claims", "policy_entities", "fragility_points", "warning_signs", "evidence_ids"],
            completion_questions=["是否覆盖政策和平台风险？", "是否说明脆弱点？", "是否避免输出违法/滥用操作步骤？"],
            safety_notes=["风险探测只能用于理解和防范，不得提供可执行的违法或滥用教程。"],
        ),
    ]
