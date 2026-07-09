"""Run narrative tool: first-person research recap."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta, ToolSpec
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema
from backend.app.providers.interfaces import ChatMessage
from backend.app.schemas import Artifact, ArtifactType


def register_narrative_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="generate_run_narrative",
            description="Write a first-person recap of how the Agent researched this domain and used evidence.",
            args_schema=schema({"reason": {"type": "string"}}),
        ),
        generate_run_narrative,
    )


async def generate_run_narrative(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    """Ask the LLM to write a first-person account of the research process."""
    if context.llm_provider is None:
        return KernelObservation(
            tool_name="generate_run_narrative",
            success=False,
            summary="无法生成调研复盘：未配置 LLM。",
            error="llm provider not configured",
        )

    state = context.state
    evidence_count = len(state.evidence_refs)
    artifact_titles = [artifact.title for artifact in context.artifacts]
    claim_count = len(state.shared_knowledge.claims)
    open_questions = [q.question for q in state.shared_knowledge.open_questions if not q.resolved][:12]
    decisions = [decision.reason for decision in state.decision_log][-20:]

    prompt = (
        "你是这次领域调研的 Agent。请用第一人称、面向普通用户，讲清楚你是怎么一步步把这个领域搞明白的。"
        "像一个人在复盘自己的研究过程，不要用内部术语（如 layer_id、ready_to_write、coverage_score）。\n\n"
        f"领域：{context.project.domain}\n"
        f"我一共收集了 {evidence_count} 条证据，提炼了 {claim_count} 条要点。\n"
        f"我最终写成的文档：{', '.join(artifact_titles) or '（无）'}\n"
        "我做过的一些判断（内部记录，供你参考，不要照抄术语）：\n"
        + "\n".join(f"- {decision}" for decision in decisions)
        + "\n\n我还没完全解决的问题：\n"
        + "\n".join(f"- {question}" for question in open_questions)
        + "\n\n请输出 Markdown，结构建议：\n"
        "## 我想搞清楚什么\n## 我是怎么找资料的\n## 中途遇到的问题和调整\n"
        "## 我最后弄明白了什么\n## 还没解决、值得继续挖的\n\n"
        "特别说明：如果收集的资料很多，请诚实说明哪些用上了、哪些暂时没用上，帮用户判断信息利用情况。"
    )
    try:
        raw = await context.llm_provider.complete([ChatMessage(role="user", content=prompt)])
    except Exception as exc:
        return KernelObservation(
            tool_name="generate_run_narrative",
            success=False,
            summary=f"调研复盘生成失败：{type(exc).__name__}",
            error=str(exc)[:300],
        )
    content = str(raw).strip()
    if len(content) < 200:
        return KernelObservation(
            tool_name="generate_run_narrative",
            success=False,
            summary="调研复盘内容过短，未保存。",
            error="narrative too short",
        )

    artifact = Artifact(
        id=f"ART-KERNEL-NARRATIVE-{uuid4().hex[:8]}",
        project_id=context.project.id,
        artifact_type=ArtifactType.FOLLOW_UP_NOTE,
        title=f"调研复盘：我是怎么研究{context.project.domain}的",
        content_path="docs/00-调研复盘.md",
        content=content,
        source_evidence_ids=list(dict.fromkeys(state.evidence_refs)),
        schema_version="v2-agent-kernel",
        created_at=datetime.now(UTC),
    )
    context.artifacts.append(artifact)
    summary = f"已生成调研复盘（{len(content)} 字符），讲清楚了本轮研究思路和信息利用情况。"
    return KernelObservation(
        tool_name="generate_run_narrative",
        success=True,
        summary=summary,
        data={"artifact": artifact.model_dump(mode="json")},
        state_delta=KernelStateDelta(artifact_ids=[artifact.id], task_notes=[summary]),
        artifact_ids=[artifact.id],
    )
