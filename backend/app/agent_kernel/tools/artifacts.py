"""Artifact writing tools for the V2 Agent Kernel."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.app.agent_kernel.context import KernelContextBuilder
from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta, ToolSpec
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema
from backend.app.agent_state.models import KnowledgeLayerId
from backend.app.providers.interfaces import ChatMessage
from backend.app.schemas import Artifact, ArtifactType


_LAYER_ARTIFACT_TYPES: dict[KnowledgeLayerId, ArtifactType] = {
    KnowledgeLayerId.PREREQUISITE: ArtifactType.LEARNING_PATH,
    KnowledgeLayerId.WHAT_WHY: ArtifactType.DOMAIN_OVERVIEW,
    KnowledgeLayerId.WHO: ArtifactType.PLAYER_MAP,
    KnowledgeLayerId.HOW: ArtifactType.PLAYER_TOOL_MAP,
    KnowledgeLayerId.MONEY: ArtifactType.REVENUE_STRUCTURE,
    KnowledgeLayerId.RISKS: ArtifactType.UNRESOLVED_QUESTIONS,
}


def register_artifact_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="write_layer_document",
            description="Write a detailed Obsidian Markdown document for a knowledge layer from current State.",
            args_schema=schema({
                "layer_id": {"type": "string"},
                "title": {"type": "string"},
                "writing_goal": {"type": "string"},
                "required_questions": {"type": "array", "items": {"type": "string"}},
            }, required=["layer_id", "title", "writing_goal"]),
        ),
        write_layer_document,
    )
    registry.register(
        ToolSpec(
            name="review_artifact",
            description="Review whether a generated artifact is detailed, evidence-linked, and useful enough.",
            args_schema=schema({"artifact_id": {"type": "string"}, "review_goal": {"type": "string"}}, required=["artifact_id"]),
        ),
        review_artifact,
    )
    registry.register(
        ToolSpec(
            name="finish_run",
            description="Finish the Agent run after enough artifacts have been written and reviewed.",
            args_schema=schema({"reason": {"type": "string"}}, required=["reason"]),
        ),
        finish_run,
    )


async def write_layer_document(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    if context.llm_provider is None:
        return KernelObservation(
            tool_name="write_layer_document",
            success=False,
            summary="写作失败：没有配置 LLM Provider，不能生成真实文档。",
            error="llm provider not configured",
        )
    context.writer_call_count += 1
    layer_id = _layer_id(tool_call.args.get("layer_id"), context.state.current_layer_id)
    if layer_id is None:
        return KernelObservation(
            tool_name="write_layer_document",
            success=False,
            summary="写作失败：缺少有效 layer_id。",
            error="invalid layer_id",
        )
    layer = context.state.knowledge_schema.layer(layer_id)
    title = str(tool_call.args.get("title") or (layer.title if layer else layer_id.value)).strip()
    writing_goal = str(tool_call.args.get("writing_goal") or (layer.goal if layer else "")).strip()
    context_text = KernelContextBuilder().build_prompt_context(
        state=context.state,
        tools=[],
        trace_tail=[],
    )
    prompt = _load_prompt("artifact_writer.md") + (
        f"\n\n# 当前写作任务\n"
        f"项目：{context.project.title}\n领域：{context.project.domain}\n"
        f"层级：{layer_id.value} / {title}\n写作目标：{writing_goal}\n"
        f"必须回答：{tool_call.args.get('required_questions') or (layer.guiding_questions if layer else [])}\n\n"
        f"# 当前 State Context\n{context_text}\n\n"
        "请只输出 Markdown 正文，不要 JSON，不要代码块包裹。"
    )
    cleaned = ""
    errors: list[str] = []
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        attempt_prompt = prompt if attempt == 1 else _retry_prompt(prompt, title=title, errors=errors, attempt=attempt)
        try:
            markdown = await context.llm_provider.complete_structured(
                [ChatMessage(role="user", content=attempt_prompt)],
                str,
            )
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:220]}")
            continue
        cleaned = _clean_markdown(str(markdown))
        if _usable_markdown(cleaned):
            break
        heading_count = cleaned.count("\n## ") + cleaned.count("\n### ")
        errors.append(
            f"attempt {attempt}: markdown too thin "
            f"(chars={len(cleaned)}, headings={heading_count})"
        )
    else:
        return KernelObservation(
            tool_name="write_layer_document",
            success=False,
            summary=f"LLM 写作连续失败，已重试 {max_attempts} 次且未保存任何模板产物：{title}",
            error="llm writing failed after retries",
            data={
                "attempts": max_attempts,
                "errors": errors,
                "generated_chars": len(cleaned),
                "heading_count": cleaned.count("\n## ") + cleaned.count("\n### "),
            },
        )

    artifact = Artifact(
        id=f"ART-KERNEL-{layer_id.value.upper()}-{uuid4().hex[:8]}",
        project_id=context.project.id,
        artifact_type=_LAYER_ARTIFACT_TYPES.get(layer_id, ArtifactType.CORE_CONCEPTS),
        title=title,
        content_path=f"{_artifact_index(layer_id)}-{_safe_filename(title)}.md",
        content=cleaned,
        source_evidence_ids=list(dict.fromkeys(context.state.evidence_refs)),
        schema_version="v2-agent-kernel",
        created_at=datetime.now(UTC),
    )
    context.artifacts.append(artifact)
    return KernelObservation(
        tool_name="write_layer_document",
        success=True,
        summary=f"已写作 V2 层级文档：{title}（{len(cleaned)} 字符）。",
        data={"artifact": artifact.model_dump(mode="json")},
        state_delta=KernelStateDelta(artifact_ids=[artifact.id]),
        artifact_ids=[artifact.id],
    )


async def review_artifact(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    artifact_id = str(tool_call.args.get("artifact_id") or "").strip()
    artifact = next((item for item in context.artifacts if item.id == artifact_id), None)
    if artifact is None:
        artifact = next((item for item in context.repository.list_artifacts(context.project.id) if item.id == artifact_id), None)
    if artifact is None:
        return KernelObservation(
            tool_name="review_artifact",
            success=False,
            summary=f"未找到待审查产物：{artifact_id}",
            error="artifact not found",
        )
    heading_count = artifact.content.count("\n## ") + artifact.content.count("\n### ")
    has_evidence = "EV-" in artifact.content or bool(artifact.source_evidence_ids)
    detailed = len(artifact.content) >= 900 and heading_count >= 2
    summary = (
        f"Artifact Review: {artifact.title} 详细度={'通过' if detailed else '不足'}，"
        f"证据关联={'有' if has_evidence else '不足'}。"
    )
    return KernelObservation(
        tool_name="review_artifact",
        success=detailed and has_evidence,
        summary=summary,
        data={"artifact_id": artifact.id, "chars": len(artifact.content), "heading_count": heading_count, "has_evidence": has_evidence},
        state_delta=KernelStateDelta(task_notes=[summary], coverage_gaps=[] if detailed and has_evidence else ["artifact_too_thin_or_missing_evidence"]),
    )


async def finish_run(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    reason = str(tool_call.args.get("reason") or "").strip()
    return KernelObservation(
        tool_name="finish_run",
        success=True,
        summary=f"Agent 决定结束运行：{reason}",
        data={"reason": reason, "artifact_count": len(context.artifacts)},
    )


def _load_prompt(name: str) -> str:
    path = Path(__file__).parents[2] / "agents" / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        "你是 SectorBreaker V2 写作者。必须基于 State 写详实的 Obsidian Markdown，"
        "引用 evidence id，使用 wikilinks，不要写空模板。"
    )


def _clean_markdown(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return cleaned


def _retry_prompt(base_prompt: str, *, title: str, errors: list[str], attempt: int) -> str:
    return (
        base_prompt
        + "\n\n# Retry Instruction\n"
        f"这是第 {attempt} 次写作重试。上一轮失败原因：\n"
        + "\n".join(f"- {error}" for error in errors[-3:])
        + "\n\n请重新生成完整、详实、可用于 Obsidian 的 Markdown 正文。"
        f"文档标题是《{title}》。不要输出解释，不要输出 JSON，不要输出占位模板。"
    )


def _usable_markdown(value: str) -> bool:
    return len(value) >= 600 and (value.count("\n## ") + value.count("\n### ")) >= 1


def _layer_id(value, fallback) -> KnowledgeLayerId | None:
    raw = str(value or "").strip()
    if raw:
        try:
            return KnowledgeLayerId(raw)
        except ValueError:
            return None
    return fallback


def _artifact_index(layer_id: KnowledgeLayerId) -> str:
    mapping = {
        KnowledgeLayerId.PREREQUISITE: "00",
        KnowledgeLayerId.WHAT_WHY: "01",
        KnowledgeLayerId.WHO: "02",
        KnowledgeLayerId.HOW: "03",
        KnowledgeLayerId.MONEY: "04",
        KnowledgeLayerId.RISKS: "05",
    }
    return mapping.get(layer_id, "50")


def _safe_filename(title: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\\s]+", "-", title).strip("-") or "artifact"
