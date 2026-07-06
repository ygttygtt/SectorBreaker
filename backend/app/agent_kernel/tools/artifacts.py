"""Artifact writing tools for the V2 Agent Kernel."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta, ToolSpec
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema
from backend.app.agent_state.models import KnowledgeLayerId
from backend.app.providers.interfaces import ChatMessage
from backend.app.schemas import Artifact, ArtifactType, RunEvent


_LAYER_ARTIFACT_TYPES: dict[str, ArtifactType] = {
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
    layer_key = _layer_value(layer_id)
    layer = context.state.knowledge_schema.layer(layer_key)
    title = str(tool_call.args.get("title") or (layer.title if layer else layer_key)).strip()
    writing_goal = str(tool_call.args.get("writing_goal") or (layer.goal if layer else "")).strip()
    context_text = _build_writer_context(context, layer_id=layer_id, title=title)
    cleaned, errors = await _write_document_in_sections(
        context,
        title=title,
        layer_id=layer_id,
        writing_goal=writing_goal,
        required_questions=tool_call.args.get("required_questions") or (layer.guiding_questions if layer else []),
        context_text=context_text,
    )
    if not _usable_markdown(cleaned):
        return KernelObservation(
            tool_name="write_layer_document",
            success=False,
            summary=f"LLM 分节写作失败，未保存任何模板产物：{title}",
            error="llm writing failed after retries",
            data={
                "attempts": len(errors),
                "errors": errors,
                "generated_chars": len(cleaned),
                "heading_count": cleaned.count("\n## ") + cleaned.count("\n### "),
            },
        )

    artifact = Artifact(
        id=f"ART-KERNEL-{layer_key.upper()}-{uuid4().hex[:8]}",
        project_id=context.project.id,
        artifact_type=_LAYER_ARTIFACT_TYPES.get(layer_key, ArtifactType.CORE_CONCEPTS),
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


async def _write_document_in_sections(
    context: KernelRuntimeContext,
    *,
    title: str,
    layer_id: KnowledgeLayerId | str,
    writing_goal: str,
    required_questions,
    context_text: str,
) -> tuple[str, list[str]]:
    base_instruction = (
        "你是 SectorBreaker V2 Artifact Writer。"
        "你的任务是基于给定 State 摘要写 Obsidian Markdown。"
        "必须具体、详实、引用 evidence id；资料不足时标注 partial/unverified 和待补证任务。"
        "不要输出 JSON，不要输出代码块，不要编造无证据事实。"
    )
    frontmatter = _frontmatter(title=title, layer_id=layer_id, context=context)
    full_document, full_errors = await _write_full_document(
        context,
        base_instruction=base_instruction,
        title=title,
        layer_id=layer_id,
        writing_goal=writing_goal,
        required_questions=required_questions,
        context_text=context_text,
        frontmatter=frontmatter,
    )
    if _usable_markdown(full_document):
        return full_document, full_errors
    if full_errors:
        return full_document, full_errors

    section_specs = [
        ("本页解决什么问题", "解释本页目标、适合谁读、当前证据覆盖到什么程度。"),
        ("核心结论", "写 3-5 条有解释的核心结论，每条说明证据状态和限制。"),
        ("机制与结构", "围绕本层目标解释关键机制、参与关系、流程或概念边界。"),
        ("证据与可信度", "列出主要 evidence id、来源质量、哪些只是 search snippet 或外部报告线索。"),
        ("待验证问题与补库任务", "列出后续需要搜索、验证、询问用户或生成卡片的任务。"),
    ]
    sections: list[str] = []
    errors: list[str] = []
    for index, (heading, goal) in enumerate(section_specs, start=1):
        section, section_errors = await _write_section(
            context,
            base_instruction=base_instruction,
            title=title,
            heading=heading,
            section_goal=goal,
            writing_goal=writing_goal,
            required_questions=required_questions,
            context_text=context_text,
            index=index,
        )
        errors.extend(section_errors)
        if section:
            sections.append(section)
        else:
            return "\n\n".join([frontmatter, f"# {title}", *sections]), errors
    markdown = "\n\n".join([frontmatter, f"# {title}", *sections]).strip()
    return markdown, errors


async def _write_full_document(
    context: KernelRuntimeContext,
    *,
    base_instruction: str,
    title: str,
    layer_id: KnowledgeLayerId | str,
    writing_goal: str,
    required_questions,
    context_text: str,
    frontmatter: str,
) -> tuple[str, list[str]]:
    errors: list[str] = []
    layer_key = _layer_value(layer_id)
    prompt = (
        f"{base_instruction}\n\n"
        "# 完整文档写作任务\n"
        f"文档标题：{title}\n"
        f"layer_id：{layer_key}\n"
        f"文档目标：{writing_goal}\n"
        f"必须回答：{required_questions}\n\n"
        f"# 写作上下文\n{context_text}\n\n"
        "# 输出要求\n"
        "请一次性输出完整 Obsidian Markdown 正文，不要输出 JSON，不要代码块包裹。\n"
        "必须从一级标题开始，不要输出 YAML front matter。\n"
        "建议结构：本页解决什么问题、核心结论、机制与结构、证据与可信度、待验证问题与补库任务。\n"
        "正文目标 1200-2200 中文字；至少 5 个二级标题；引用 evidence id 或明确标注待补证。\n"
        "如果证据薄弱，不要编造，写成 partial/unverified 并列出下一轮补库任务。\n"
    )
    for attempt in range(1, 3):
        attempt_prompt = prompt
        if attempt > 1:
            attempt_prompt += (
                "\n\n# Retry Instruction\n"
                f"上一轮失败原因：{errors[-1] if errors else '未知'}。\n"
                "请重新输出更完整的 Markdown，保持结构清楚、证据关联明确。"
            )
        try:
            output = await _complete_text_with_heartbeat(
                context,
                [ChatMessage(role="user", content=attempt_prompt)],
                title=f"{title} / 完整文档",
                attempt=attempt,
            )
        except Exception as exc:
            errors.append(f"full document attempt {attempt}: {type(exc).__name__}: {str(exc)[:260]}")
            continue
        cleaned = _clean_markdown(str(output))
        if not cleaned.startswith("# "):
            cleaned = f"# {title}\n\n{cleaned}"
        markdown = "\n\n".join([frontmatter, cleaned]).strip()
        if _usable_markdown(markdown):
            return markdown, errors
        errors.append(
            f"full document attempt {attempt}: unusable "
            f"(chars={len(markdown)}, heading_count={markdown.count(chr(10) + '## ') + markdown.count(chr(10) + '### ')})"
        )
    return "\n\n".join([frontmatter, f"# {title}"]).strip(), errors


async def _write_section(
    context: KernelRuntimeContext,
    *,
    base_instruction: str,
    title: str,
    heading: str,
    section_goal: str,
    writing_goal: str,
    required_questions,
    context_text: str,
    index: int,
) -> tuple[str, list[str]]:
    errors: list[str] = []
    max_attempts = 2
    prompt = (
        f"{base_instruction}\n\n"
        "# 分节写作任务\n"
        f"文档标题：{title}\n"
        f"文档目标：{writing_goal}\n"
        f"必须回答：{required_questions}\n"
        f"当前章节：## {heading}\n"
        f"章节目标：{section_goal}\n\n"
        f"# 写作上下文\n{context_text}\n\n"
        "请只输出这一节 Markdown，从二级标题开始，例如 `## 本页解决什么问题`。"
        "不要输出 YAML，不要输出文档总标题，不要输出 JSON，不要代码块包裹。"
        "本节写 300-700 中文字；必须具体、详实、引用 evidence id 或明确标注待补证。"
    )
    for attempt in range(1, max_attempts + 1):
        attempt_prompt = prompt
        if attempt > 1:
            attempt_prompt += (
                "\n\n# Retry Instruction\n"
                f"上一轮失败原因：{errors[-1] if errors else '未知'}。\n"
                f"请重新输出 `## {heading}` 这一节，保持 300-700 中文字。"
            )
        try:
            output = await _complete_text_with_heartbeat(
                context,
                [ChatMessage(role="user", content=attempt_prompt)],
                title=f"{title} / {heading}",
                attempt=attempt,
            )
        except Exception as exc:
            errors.append(f"section {index} {heading} attempt {attempt}: {type(exc).__name__}: {str(exc)[:260]}")
            continue
        cleaned = _clean_markdown(str(output))
        if not cleaned.startswith("## "):
            cleaned = f"## {heading}\n\n{cleaned}"
        if len(cleaned) >= 180:
            return cleaned, errors
        errors.append(
            f"section {index} {heading} attempt {attempt}: too thin "
            f"(chars={len(cleaned)}, preview={cleaned[:180]!r})"
        )
    return "", errors


def _frontmatter(*, title: str, layer_id: KnowledgeLayerId | str, context: KernelRuntimeContext) -> str:
    evidence_lines = "\n".join(f'  - "{item}"' for item in list(dict.fromkeys(context.state.evidence_refs))[:20])
    layer_key = _layer_value(layer_id)
    return (
        "---\n"
        'schema_version: "v2-agent-kernel"\n'
        'type: "layer_artifact"\n'
        f'layer_id: "{layer_key}"\n'
        'status: "draft"\n'
        'confidence: "partial"\n'
        "evidence_ids:\n"
        f"{evidence_lines if evidence_lines else '  []'}\n"
        'tags: ["sectorbreaker", "domain-knowledge"]\n'
        "---"
    )


def _load_prompt(name: str) -> str:
    path = Path(__file__).parents[2] / "agents" / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        "你是 SectorBreaker V2 写作者。必须基于 State 写详实的 Obsidian Markdown，"
        "引用 evidence id，使用 wikilinks，不要写空模板。"
    )


def _build_writer_context(context: KernelRuntimeContext, *, layer_id: KnowledgeLayerId | str, title: str) -> str:
    """Build a compact writer-only context so text generation does not drown in tool specs."""

    state = context.state
    layer_key = _layer_value(layer_id)
    layer = state.knowledge_schema.layer(layer_key)
    relevant_sources = [
        source for source in state.shared_knowledge.source_memories
        if not source.related_layer_ids or layer_key in {_layer_value(item) for item in source.related_layer_ids}
    ][-10:]
    relevant_claims = [
        claim for claim in state.shared_knowledge.claims
        if not claim.layer_ids or layer_key in {_layer_value(item) for item in claim.layer_ids}
    ][-16:]
    open_questions = [
        question for question in state.shared_knowledge.open_questions
        if not question.layer_ids or layer_key in {_layer_value(item) for item in question.layer_ids}
    ][-10:]
    evidence_rows = []
    for evidence_id in state.evidence_refs[-14:]:
        try:
            evidence = context.repository.get_evidence(evidence_id)
        except Exception:
            continue
        evidence_rows.append(
            f"- {evidence.id}: {evidence.source_title} | "
            f"status={evidence.verification_status.value}, quality={evidence.source_quality.value} | "
            f"{(evidence.summary or evidence.snippet or '')[:360]}"
        )
    source_rows = [
        f"- {source.title or source.source_id} | trust={source.trust_level.value} | "
        f"evidence={','.join(source.evidence_ids) or '待补证'} | {source.summary[:420]}"
        for source in relevant_sources
    ]
    claim_rows = [
        f"- {claim.text} | trust={claim.trust_level.value}, status={claim.verification_status}, "
        f"evidence={','.join(claim.evidence_ids) or '待补证'}"
        for claim in relevant_claims
    ]
    question_rows = [f"- {question.question} | reason={question.reason[:180]}" for question in open_questions]
    layer_questions = "\n".join(f"- {item}" for item in (layer.guiding_questions if layer else []))
    layer_criteria = "\n".join(f"- {item}" for item in (layer.completion_criteria if layer else []))
    return (
        "## Project\n"
        f"- title: {context.project.title}\n"
        f"- domain: {context.project.domain}\n"
        f"- market_scope: {context.project.market_scope.value}\n"
        f"- source_policy: {context.project.source_policy.value}\n"
        f"- user_goal: {state.meta_context.user_goal}\n\n"
        "## Current Writing Layer\n"
        f"- layer_id: {layer_key}\n"
        f"- title: {title}\n"
        f"- layer_goal: {(layer.goal if layer else '')}\n"
        f"- guiding_questions:\n{layer_questions or '- 未指定'}\n"
        f"- completion_criteria:\n{layer_criteria or '- 未指定'}\n\n"
        "## Evidence Ledger Snippets\n"
        + ("\n".join(evidence_rows) if evidence_rows else "- 暂无 evidence id，必须写成待补证初稿并说明阻断/缺口。")
        + "\n\n## Source Memories\n"
        + ("\n".join(source_rows) if source_rows else "- 暂无 source memory。")
        + "\n\n## Claims\n"
        + ("\n".join(claim_rows) if claim_rows else "- 暂无结构化 claim。")
        + "\n\n## Open Questions\n"
        + ("\n".join(question_rows) if question_rows else "- 暂无。")
        + "\n\n## Output Constraints\n"
        "- 只输出 Markdown 正文，不输出 JSON。\n"
        "- 目标长度 1500-3000 中文字；优先详实清楚，不要写成长篇废话。\n"
        "- 至少包含 5 个二级标题，并在正文中引用可用 evidence id。\n"
        "- 资料薄弱处必须标注 partial/unverified，并列入待验证问题。\n"
    )


async def _complete_text_with_heartbeat(
    context: KernelRuntimeContext,
    messages: list[ChatMessage],
    *,
    title: str,
    attempt: int,
) -> str:
    task = asyncio.create_task(context.llm_provider.complete(messages))  # type: ignore[union-attr]
    waited = 0
    while not task.done():
        await asyncio.sleep(15)
        waited += 15
        if task.done():
            break
        await context.emit_event(RunEvent(
            event_type="node_progress",
            gate="artifact_writing",
            agent="V2 Artifact Writer",
            message=f"仍在写作：{title}，LLM 正在生成 Markdown 正文（第 {attempt} 次，已等待约 {waited} 秒）",
            severity="info",
        ))
    return await task


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


def _layer_id(value, fallback) -> KnowledgeLayerId | str | None:
    raw = str(value or "").strip()
    if raw:
        try:
            return KnowledgeLayerId(raw)
        except ValueError:
            return raw
    return fallback


def _artifact_index(layer_id: KnowledgeLayerId | str) -> str:
    mapping = {
        KnowledgeLayerId.PREREQUISITE.value: "00",
        KnowledgeLayerId.WHAT_WHY.value: "01",
        KnowledgeLayerId.WHO.value: "02",
        KnowledgeLayerId.HOW.value: "03",
        KnowledgeLayerId.MONEY.value: "04",
        KnowledgeLayerId.RISKS.value: "05",
    }
    return mapping.get(_layer_value(layer_id), "50")


def _safe_filename(title: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\\s]+", "-", title).strip("-") or "artifact"


def _layer_value(layer_id) -> str:
    return layer_id.value if hasattr(layer_id, "value") else str(layer_id)
