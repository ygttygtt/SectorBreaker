"""Three universal knowledge anchors present in every SectorBreaker schema."""
from __future__ import annotations

from backend.app.agent_state.models import KnowledgeLayer, KnowledgeLayerId


def build_universal_anchors(domain: str) -> list[KnowledgeLayer]:
    """Return the three immutable anchor layers for any domain."""
    return [
        KnowledgeLayer(
            id=KnowledgeLayerId.WHAT_WHY,
            title="本源与边界",
            goal="解释 " + domain + " 是什么、为什么存在、解决谁的什么问题，以及它的核心边界。",
            priority_weight=2.0,
            guiding_questions=[
                "它是什么？",
                "为什么会产生这个需求？",
                "解决谁的什么痛点？",
                "它与相邻领域的边界在哪里？",
            ],
            completion_criteria=[
                "能用外行能懂的语言说明领域存在理由。",
                "能列出 2-3 个典型使用场景。",
                "能说明它不做什么（边界）。",
            ],
            required_evidence_types=["overview", "official_or_report", "example"],
            is_universal_anchor=True,
        ),
        KnowledgeLayer(
            id=KnowledgeLayerId.WHO,
            title="参与者生态",
            goal="识别 " + domain + " 中的用户、提供方、头部玩家、关键资源持有者及其关系。",
            priority_weight=1.8,
            guiding_questions=[
                "谁在用？",
                "谁在提供？",
                "主流玩家是谁？",
                "关键资源掌握在谁手里？",
            ],
            completion_criteria=[
                "能列出主要角色类型。",
                "能描述角色之间的核心关系或依赖。",
            ],
            required_evidence_types=["player", "case", "community_or_company"],
            is_universal_anchor=True,
        ),
        KnowledgeLayer(
            id=KnowledgeLayerId.HOW,
            title="运行机制",
            goal="拆解 " + domain + " 的实现原理、核心流程、工具/框架，以及初学者容易卡住的隐藏术语。",
            priority_weight=1.6,
            guiding_questions=[
                "它怎么实现？",
                "关键流程是什么？",
                "需要什么工具 / 框架 / 前置概念？",
                "哪些术语会让新手卡住？",
            ],
            completion_criteria=[
                "能说明核心工作原理。",
                "能列出关键工具或步骤。",
                "能把未知术语转成待下钻任务。",
            ],
            required_evidence_types=["technical_doc", "tutorial", "implementation_case"],
            is_universal_anchor=True,
        ),
    ]


UNIVERSAL_ANCHOR_IDS: frozenset[str] = frozenset({
    KnowledgeLayerId.WHAT_WHY.value,
    KnowledgeLayerId.WHO.value,
    KnowledgeLayerId.HOW.value,
})
