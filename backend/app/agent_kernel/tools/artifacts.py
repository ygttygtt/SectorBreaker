"""Artifact writing tools for the V3 Agent Kernel."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta, ToolSpec
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema
from backend.app.agent_state.models import KnowledgeLayerId
from backend.app.knowledge_base import ChangeSetService
from backend.app.providers.interfaces import ChatMessage
from backend.app.schemas import Artifact, ArtifactType, ChangeSetProposalRequest, RunEvent


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
            name="write_explainer_card",
            description=(
                "Write a focused Obsidian knowledge card for a concept, tool, player, risk, "
                "process, or drill-down question discovered during the Agent run."
            ),
            args_schema=schema({
                "card_kind": {
                    "type": "string",
                    "description": "concept | tool | player | risk | process | question | note",
                },
                "title": {"type": "string"},
                "focus": {"type": "string"},
                "layer_id": {"type": "string"},
                "writing_goal": {"type": "string"},
                "linked_artifact_ids": {"type": "array", "items": {"type": "string"}},
            }, required=["title", "focus", "writing_goal"]),
        ),
        write_explainer_card,
    )
    registry.register(
        ToolSpec(
            name="write_explainer_cards_batch",
            description=(
                "Write several independent Obsidian knowledge cards in one batch. "
                "Use this only for optional explainer cards that do not depend on each other."
            ),
            args_schema=schema({
                "cards": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "card_kind": {"type": "string"},
                            "title": {"type": "string"},
                            "focus": {"type": "string"},
                            "layer_id": {"type": "string"},
                            "writing_goal": {"type": "string"},
                            "linked_artifact_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["title", "focus", "writing_goal"],
                    },
                }
            }, required=["cards"]),
        ),
        write_explainer_cards_batch,
    )
    registry.register(
        ToolSpec(
            name="write_vault_index",
            description="Write an Obsidian navigation/index page that connects main documents, cards, evidence, and open questions.",
            args_schema=schema({
                "title": {"type": "string"},
                "index_goal": {"type": "string"},
            }, required=["title", "index_goal"]),
        ),
        write_vault_index,
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
            name="revise_layer_document",
            description=(
                "Draft a complete revision of an existing document from current State knowledge, "
                "then create a base-hash protected ChangeSet for human or policy review. "
                "This tool never activates the revision directly."
            ),
            args_schema=schema({
                "artifact_id": {"type": "string", "description": "ID of the artifact to revise"},
                "layer_id": {"type": "string"},
                "revision_goal": {"type": "string", "description": "What to improve or add"},
            }, required=["artifact_id", "revision_goal"]),
        ),
        revise_layer_document,
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
    budget_error = _creation_budget_error(context)
    if budget_error:
        return _budget_observation("write_layer_document", budget_error)
    context.consume_writer_call()
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
    budget_error = _creation_budget_error(context, additional_bytes=len(cleaned.encode("utf-8")))
    if budget_error:
        return _budget_observation("write_layer_document", budget_error)

    artifact = Artifact(
        id=f"ART-KERNEL-{layer_key.upper()}-{uuid4().hex[:8]}",
        project_id=context.project.id,
        artifact_type=_LAYER_ARTIFACT_TYPES.get(layer_key, ArtifactType.CORE_CONCEPTS),
        title=title,
        content_path=f"{_artifact_index(layer_id)}-{_safe_filename(title)}.md",
        content=cleaned,
        source_evidence_ids=list(dict.fromkeys(context.state.evidence_refs)),
        schema_version="v3-knowledge-ops",
        created_at=datetime.now(UTC),
        run_id=context.run_id,
    )
    context.artifacts.append(artifact)
    return KernelObservation(
        tool_name="write_layer_document",
        success=True,
        summary=f"已写作 V3 知识文档：{title}（{len(cleaned)} 字符）。",
        data={"artifact": artifact.model_dump(mode="json")},
        state_delta=KernelStateDelta(artifact_ids=[artifact.id]),
        artifact_ids=[artifact.id],
    )


async def write_explainer_card(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    if context.llm_provider is None:
        return KernelObservation(
            tool_name="write_explainer_card",
            success=False,
            summary="解释卡写作失败：没有配置 LLM Provider。",
            error="llm provider not configured",
        )
    budget_error = _creation_budget_error(context)
    if budget_error:
        return _budget_observation("write_explainer_card", budget_error)
    if context.writer_call_count >= context.state.autonomy_policy.max_writer_calls:
        return _budget_observation("write_explainer_card", "writer budget exhausted")
    context.consume_writer_call()
    title = str(tool_call.args.get("title") or "").strip()
    focus = str(tool_call.args.get("focus") or title).strip()
    if not title and focus:
        title = focus[:60].strip()
    if not focus and title:
        focus = title
    writing_goal = str(tool_call.args.get("writing_goal") or "").strip()
    if not title or not focus:
        return KernelObservation(
            tool_name="write_explainer_card",
            success=False,
            summary="解释卡写作失败：缺少 title 或 focus。",
            error="missing title or focus",
        )
    card_kind = _card_kind(tool_call.args.get("card_kind"))
    layer_id = _layer_id(tool_call.args.get("layer_id"), context.state.current_layer_id)
    context_text = _build_writer_context(context, layer_id=layer_id or "dynamic_card", title=title)
    cleaned, errors = await _write_card_document(
        context,
        title=title,
        focus=focus,
        card_kind=card_kind,
        writing_goal=writing_goal,
        context_text=context_text,
    )
    if not _usable_card_markdown(cleaned):
        return KernelObservation(
            tool_name="write_explainer_card",
            success=False,
            summary=f"解释卡写作失败，未保存模板产物：{title}",
            error="llm card writing failed after retries",
            data={"attempts": len(errors), "errors": errors, "generated_chars": len(cleaned)},
        )
    budget_error = _creation_budget_error(context, additional_bytes=len(cleaned.encode("utf-8")))
    if budget_error:
        return _budget_observation("write_explainer_card", budget_error)

    artifact = _build_artifact(
        context,
        artifact_id=f"ART-KERNEL-CARD-{uuid4().hex[:8]}",
        artifact_type=_card_artifact_type(card_kind),
        title=title,
        content_path=f"{_card_folder(card_kind)}/{_safe_filename(title)}.md",
        content=cleaned,
        source_evidence_ids=list(dict.fromkeys(context.state.evidence_refs)),
        schema_version="v3-knowledge-ops",
    )
    context.artifacts.append(artifact)
    summary = f"已写作解释性知识卡：{title}（{card_kind}，{len(cleaned)} 字符）。"
    return KernelObservation(
        tool_name="write_explainer_card",
        success=True,
        summary=summary,
        data={
            "artifact": artifact.model_dump(mode="json"),
            "card_kind": card_kind,
            "linked_artifact_ids": list(tool_call.args.get("linked_artifact_ids") or []),
        },
        state_delta=KernelStateDelta(artifact_ids=[artifact.id], task_notes=[summary]),
        artifact_ids=[artifact.id],
    )


async def write_explainer_cards_batch(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    if context.llm_provider is None:
        return KernelObservation(
            tool_name="write_explainer_cards_batch",
            success=False,
            summary="批量解释卡写作失败：没有配置 LLM Provider。",
            error="llm provider not configured",
        )
    raw_cards = tool_call.args.get("cards") or []
    if not isinstance(raw_cards, list) or not raw_cards:
        return KernelObservation(
            tool_name="write_explainer_cards_batch",
            success=False,
            summary="批量解释卡写作失败：没有提供 cards。",
            error="missing cards",
        )
    remaining_files = context.state.autonomy_policy.max_files_per_run - len(context.new_artifacts())
    remaining_writers = context.state.autonomy_policy.max_writer_calls - context.writer_call_count
    allowed_count = max(0, min(6, remaining_files, remaining_writers))
    cards = [card for card in raw_cards[:allowed_count] if isinstance(card, dict)]
    if not cards:
        return KernelObservation(
            tool_name="write_explainer_cards_batch",
            success=False,
            summary="批量解释卡写作被硬预算阻断，或 cards 格式无效。",
            error="batch card budget exhausted or invalid cards",
            requires_human=allowed_count == 0,
        )

    async def write_one(card: dict) -> KernelObservation:
        card_args = {
            "card_kind": card.get("card_kind") or "concept",
            "title": card.get("title") or card.get("focus") or "",
            "focus": card.get("focus") or card.get("title") or "",
            "layer_id": card.get("layer_id") or tool_call.args.get("layer_id"),
            "writing_goal": card.get("writing_goal") or "补充主文档之外的解释性知识卡。",
            "linked_artifact_ids": card.get("linked_artifact_ids") or [],
        }
        return await write_explainer_card(
            tool_call.model_copy(update={
                "tool_name": "write_explainer_card",
                "args": card_args,
                "reason": f"批量解释卡：{card_args['title']}",
            }),
            context,
        )

    observations = await asyncio.gather(*(write_one(card) for card in cards))
    successful_ids = [artifact_id for obs in observations if obs.success for artifact_id in obs.artifact_ids]
    failed = [
        {
            "title": str(cards[index].get("title") or cards[index].get("focus") or f"card-{index + 1}"),
            "summary": obs.summary,
            "error": obs.error,
        }
        for index, obs in enumerate(observations)
        if not obs.success
    ]
    summary = f"批量解释卡完成：成功 {len(successful_ids)} 张，失败 {len(failed)} 张。"
    return KernelObservation(
        tool_name="write_explainer_cards_batch",
        success=bool(successful_ids),
        summary=summary,
        error="" if successful_ids else "all cards failed",
        data={
            "artifact_ids": successful_ids,
            "failed_cards": failed,
            "requested_count": len(cards),
        },
        state_delta=KernelStateDelta(artifact_ids=successful_ids, task_notes=[summary]),
        artifact_ids=successful_ids,
    )


async def write_vault_index(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    title = str(tool_call.args.get("title") or f"{context.project.title} 知识库导航").strip()
    index_goal = str(tool_call.args.get("index_goal") or "连接本轮主文档、解释卡、证据和后续补库任务。").strip()
    if not context.artifacts:
        return KernelObservation(
            tool_name="write_vault_index",
            success=False,
            summary="知识库导航写作失败：当前没有任何 artifact 可索引。",
            error="no artifacts to index",
        )
    budget_error = _creation_budget_error(context)
    if budget_error:
        return _budget_observation("write_vault_index", budget_error)
    content = _render_vault_index_markdown(context, title=title, index_goal=index_goal)
    budget_error = _creation_budget_error(context, additional_bytes=len(content.encode("utf-8")))
    if budget_error:
        return _budget_observation("write_vault_index", budget_error)
    artifact = _build_artifact(
        context,
        artifact_id=f"ART-KERNEL-INDEX-{uuid4().hex[:8]}",
        artifact_type=ArtifactType.EXPORT_MANIFEST,
        title=title,
        content_path="00-知识库导航.md",
        content=content,
        source_evidence_ids=list(dict.fromkeys(context.state.evidence_refs)),
        schema_version="v3-knowledge-ops",
    )
    context.artifacts.append(artifact)
    summary = f"已写作知识库导航页：{title}（连接 {len(context.artifacts) - 1} 个已有产物）。"
    return KernelObservation(
        tool_name="write_vault_index",
        success=True,
        summary=summary,
        data={"artifact": artifact.model_dump(mode="json")},
        state_delta=KernelStateDelta(artifact_ids=[artifact.id], task_notes=[summary]),
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


async def revise_layer_document(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    if context.llm_provider is None:
        return KernelObservation(
            tool_name="revise_layer_document",
            success=False,
            summary="修订失败：没有配置 LLM Provider。",
            error="llm provider not configured",
        )
    artifact_id = str(tool_call.args.get("artifact_id") or "").strip()
    revision_goal = str(tool_call.args.get("revision_goal") or "").strip()
    old_artifact = next((a for a in context.artifacts if a.id == artifact_id), None)
    if old_artifact is None:
        return KernelObservation(
            tool_name="revise_layer_document",
            success=False,
            summary=f"修订失败：找不到 artifact_id={artifact_id}。",
            error="artifact not found",
        )
    context.consume_writer_call()
    layer_id = tool_call.args.get("layer_id") or old_artifact.content_path or artifact_id
    context_text = _build_writer_context(context, layer_id=layer_id, title=old_artifact.title)
    revision_prompt = (
        "你正在修订一篇已有的 Obsidian 领域知识文档。\n\n"
        "原文档标题：" + old_artifact.title + "\n"
        "修订目标：" + revision_goal + "\n\n"
        "原文档内容（参考，不要完全复制）：\n"
        + old_artifact.content[:3000]
        + "\n\n当前 Agent State 新增的知识上下文：\n"
        + context_text
        + "\n\n请输出修订后的完整 Obsidian Markdown 文档。\n"
        "要求：\n"
        "- 保留原文档的核心结构，吸收新增知识和证据；\n"
        "- 补充原文档薄弱的章节，使每节有 2-3 段正文；\n"
        "- 新增的关键事实使用 [^EV-KERNEL-xxx] 脚注引用；\n"
        "- 直接输出 Markdown，不要 JSON，不要多余解释。"
    )
    try:
        from backend.app.providers.interfaces import ChatMessage
        raw = await context.llm_provider.complete(
            [ChatMessage(role="user", content=revision_prompt)]
        )
        cleaned = _clean_markdown(raw)
    except Exception as exc:
        return KernelObservation(
            tool_name="revise_layer_document",
            success=False,
            summary=f"LLM 修订失败：{type(exc).__name__}",
            error=str(exc)[:300],
        )
    if not _usable_markdown(cleaned):
        return KernelObservation(
            tool_name="revise_layer_document",
            success=False,
            summary=f"LLM 修订输出内容不足，未保存：{old_artifact.title}",
            error="revised content too thin",
        )
    evidence_ids = list(dict.fromkeys(context.state.evidence_refs))
    try:
        change_set = ChangeSetService(context.repository).propose(
            context.project.id,
            ChangeSetProposalRequest(
                summary=f"修订 {old_artifact.title}：{revision_goal}",
                path=old_artifact.content_path,
                after_content=cleaned,
                evidence_ids=evidence_ids,
                factual_change=True,
            ),
            actor="master_agent",
            run_id=context.run_id,
        )
    except Exception as exc:
        return KernelObservation(
            tool_name="revise_layer_document",
            success=False,
            summary=f"修订稿已生成，但 ChangeSet 创建失败：{old_artifact.title}",
            error=f"{type(exc).__name__}: {str(exc)[:300]}",
        )
    summary = (
        f"已生成文档修订提案：{old_artifact.title}（{len(cleaned)} 字符），"
        f"ChangeSet={change_set.id}，尚未应用。"
    )
    return KernelObservation(
        tool_name="revise_layer_document",
        success=True,
        summary=summary,
        data={
            "change_set": change_set.model_dump(mode="json"),
            "old_artifact_id": artifact_id,
            "base_hash": old_artifact.content_hash,
        },
        state_delta=KernelStateDelta(task_notes=[summary]),
        requires_human=True,
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
        "你是 SectorBreaker V3 Artifact Writer。"
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

    section_specs = [
        ("本页解决什么问题", "解释本页目标、适合谁读、当前证据覆盖到什么程度。"),
        ("核心结论", "写 3-5 条有解释的核心结论，每条说明证据状态和限制。"),
        ("机制与结构", "围绕本层目标解释关键机制、参与关系、流程或概念边界。"),
        ("证据与可信度", "列出主要 evidence id、来源质量、哪些只是 search snippet 或外部报告线索。"),
        ("待验证问题与补库任务", "列出后续需要搜索、验证、询问用户或生成卡片的任务。"),
    ]
    sections: list[str] = []
    errors: list[str] = list(full_errors)
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


async def _write_card_document(
    context: KernelRuntimeContext,
    *,
    title: str,
    focus: str,
    card_kind: str,
    writing_goal: str,
    context_text: str,
) -> tuple[str, list[str]]:
    errors: list[str] = []
    prompt = (
        "你是 SectorBreaker V3 Explainer Card Writer。"
        "你的任务是把主文档中读者可能不懂、但又影响理解的概念/流程/风险/工具写成独立 Obsidian 卡片。"
        "必须基于 State 摘要和 evidence id，不要输出 JSON，不要输出代码块，不要编造无证据事实。\n\n"
        "# 卡片任务\n"
        f"- title: {title}\n"
        f"- card_kind: {card_kind}\n"
        f"- focus: {focus}\n"
        f"- writing_goal: {writing_goal}\n\n"
        f"# 写作上下文\n{context_text}\n\n"
        "# 输出要求\n"
        "请输出完整 Obsidian Markdown 正文，不要 YAML front matter。\n"
        "必须从一级标题开始；正文 600-1400 中文字；至少 4 个二级标题。\n"
        "建议结构：一句话解释、为什么它重要、它如何运作、和本领域主文档的关系、证据与待验证。\n"
        "必须包含 2-5 个 `[[双向链接]]`，链接到相关概念或主文档标题；能引用 evidence id 就引用，不能则标注待补证。\n"
    )
    for attempt in range(1, 4):
        attempt_prompt = prompt
        if attempt > 1:
            attempt_prompt += (
                "\n\n# Retry Instruction\n"
                f"上一轮失败原因：{errors[-1] if errors else '未知'}。\n"
                "请重写为更完整的 Obsidian 知识卡片，避免空泛定义。"
            )
        try:
            output = await _complete_text_with_heartbeat(
                context,
                [ChatMessage(role="user", content=attempt_prompt)],
                title=f"{title} / 解释卡",
                attempt=attempt,
            )
        except Exception as exc:
            errors.append(f"card attempt {attempt}: {type(exc).__name__}: {str(exc)[:260]}")
            continue
        cleaned = _clean_markdown(str(output))
        if not cleaned.startswith("# "):
            cleaned = f"# {title}\n\n{cleaned}"
        frontmatter = _card_frontmatter(title=title, card_kind=card_kind, context=context)
        markdown = "\n\n".join([frontmatter, cleaned]).strip()
        if _usable_card_markdown(markdown):
            return markdown, errors
        errors.append(
            f"card attempt {attempt}: unusable "
            f"(chars={len(markdown)}, heading_count={markdown.count(chr(10) + '## ') + markdown.count(chr(10) + '### ')})"
        )
    return "\n\n".join([_card_frontmatter(title=title, card_kind=card_kind, context=context), f"# {title}"]).strip(), errors


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
        'schema_version: "v3-knowledge-ops"\n'
        'type: "layer_artifact"\n'
        f'layer_id: "{layer_key}"\n'
        'status: "draft"\n'
        'confidence: "partial"\n'
        "evidence_ids:\n"
        f"{evidence_lines if evidence_lines else '  []'}\n"
        'tags: ["sectorbreaker", "domain-knowledge"]\n'
        "---"
    )


def _card_frontmatter(*, title: str, card_kind: str, context: KernelRuntimeContext) -> str:
    evidence_lines = "\n".join(f'  - "{item}"' for item in list(dict.fromkeys(context.state.evidence_refs))[:20])
    return (
        "---\n"
        'schema_version: "v3-knowledge-ops"\n'
        'type: "knowledge_card"\n'
        f'card_kind: "{card_kind}"\n'
        'status: "draft"\n'
        'confidence: "partial"\n'
        "evidence_ids:\n"
        f"{evidence_lines if evidence_lines else '  []'}\n"
        'tags: ["sectorbreaker", "domain-knowledge", "knowledge-card"]\n'
        "---"
    )


def _load_prompt(name: str) -> str:
    path = Path(__file__).parents[2] / "agents" / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        "你是 SectorBreaker V3 写作者。必须基于 State 写详实的 Obsidian Markdown，"
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


def _render_vault_index_markdown(context: KernelRuntimeContext, *, title: str, index_goal: str) -> str:
    artifacts = list(context.artifacts)
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d")
    main_types = set(_LAYER_ARTIFACT_TYPES.values())
    card_folders = {"concepts", "tools", "players", "risks", "processes", "questions", "notes", "cards"}
    cards = [
        item for item in artifacts
        if Path(item.content_path).parts and Path(item.content_path).parts[0] in card_folders
    ]
    main_docs = [item for item in artifacts if item.artifact_type in main_types and item not in cards]
    other = [item for item in artifacts if item not in main_docs and item not in cards]
    lines = [
        "---",
        'schema_version: "v3-knowledge-ops"',
        'type: "vault_index"',
        'status: "draft"',
        f'generated_at: "{generated_at}"',
        'tags: ["sectorbreaker", "vault-index"]',
        "---\n",
        f"# {title}\n",
        f"{index_goal}\n",
        "## 推荐阅读顺序\n",
    ]
    for index, artifact in enumerate(main_docs, start=1):
        lines.append(f"{index}. [[{Path(artifact.content_path).stem}]] — {artifact.title}")
    if cards:
        lines.extend(["", "## 解释性知识卡\n"])
        by_folder: dict[str, list[Artifact]] = {}
        for card in cards:
            folder = Path(card.content_path).parts[0] if "/" in card.content_path else "cards"
            by_folder.setdefault(folder, []).append(card)
        for folder, folder_cards in sorted(by_folder.items()):
            lines.append(f"### {folder}\n")
            for card in sorted(folder_cards, key=lambda item: item.title):
                lines.append(f"- [[{Path(card.content_path).stem}]] — {card.title}")
            lines.append("")
    if other:
        lines.extend(["## 其他产物\n"])
        for artifact in other:
            lines.append(f"- [[{Path(artifact.content_path).stem}]] — {artifact.title}")
    open_questions = [question for question in context.state.shared_knowledge.open_questions if question.status != "resolved"]
    lines.extend([
        "",
        "## 证据与状态\n",
        f"- 本轮证据数量：{len(context.state.evidence_refs)}",
        f"- 当前产物数量：{len(artifacts)}",
        f"- 未解决/下钻问题：{len(open_questions)}",
        "- 证据账本：[[evidence-ledger]]",
        "",
        "## 后续补库建议\n",
    ])
    if open_questions:
        for question in open_questions[:12]:
            lines.append(f"- {question.question}（{question.reason[:80]}）")
    else:
        lines.append("- 暂无显式未解决问题；下一轮可从读者反馈中生成新卡片。")
    return "\n".join(lines).strip()


async def _complete_text_with_heartbeat(
    context: KernelRuntimeContext,
    messages: list[ChatMessage],
    *,
    title: str,
    attempt: int,
) -> str:
    task = asyncio.create_task(context.llm_provider.complete(messages))  # type: ignore[union-attr]
    waited = 0
    while True:
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=15)
        except TimeoutError:
            waited += 15
            await context.emit_event(RunEvent(
                event_type="node_progress",
                gate="artifact_writing",
                agent="V3 Artifact Writer",
                message=f"仍在写作：{title}，LLM 正在生成 Markdown 正文（第 {attempt} 次，已等待约 {waited} 秒）",
                severity="info",
            ))
        except Exception:
            raise
        if task.done():
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


def _usable_card_markdown(value: str) -> bool:
    return len(value) >= 500 and value.lstrip().startswith("---") and (
        value.count("\n## ") + value.count("\n### ")
    ) >= 2


def _build_artifact(
    context: KernelRuntimeContext,
    *,
    artifact_id: str,
    artifact_type: ArtifactType,
    title: str,
    content_path: str,
    content: str,
    source_evidence_ids: list[str],
    schema_version: str,
) -> Artifact:
    return Artifact(
        id=artifact_id,
        project_id=context.project.id,
        artifact_type=artifact_type,
        title=title,
        content_path=content_path,
        content=content,
        source_evidence_ids=source_evidence_ids,
        schema_version=schema_version,
        created_at=datetime.now(UTC),
        run_id=context.run_id,
    )


def _creation_budget_error(context: KernelRuntimeContext, *, additional_bytes: int = 0) -> str:
    new_artifacts = context.new_artifacts()
    policy = context.state.autonomy_policy
    if len(new_artifacts) >= policy.max_files_per_run:
        return "max_files_per_run exhausted"
    changed_bytes = sum(len(item.content.encode("utf-8")) for item in new_artifacts) + additional_bytes
    if changed_bytes > policy.max_changed_bytes:
        return "max_changed_bytes exhausted"
    return ""


def _budget_observation(tool_name: str, error: str) -> KernelObservation:
    return KernelObservation(
        tool_name=tool_name,
        success=False,
        summary=f"写入预算已阻断操作：{error}。",
        error=error,
        requires_human=True,
    )


def _card_kind(value) -> str:
    raw = str(value or "concept").strip().lower()
    return raw if raw in {"concept", "tool", "player", "risk", "process", "question", "note"} else "concept"


def _card_folder(card_kind: str) -> str:
    return {
        "concept": "concepts",
        "tool": "tools",
        "player": "players",
        "risk": "risks",
        "process": "processes",
        "question": "questions",
        "note": "notes",
    }.get(card_kind, "concepts")


def _card_artifact_type(card_kind: str) -> ArtifactType:
    return {
        "concept": ArtifactType.CORE_CONCEPTS,
        "tool": ArtifactType.PLAYER_TOOL_MAP,
        "player": ArtifactType.PLAYER_MAP,
        "risk": ArtifactType.UNRESOLVED_QUESTIONS,
        "process": ArtifactType.PLAYER_TOOL_MAP,
        "question": ArtifactType.UNRESOLVED_QUESTIONS,
        "note": ArtifactType.CORE_CONCEPTS,
    }.get(card_kind, ArtifactType.CORE_CONCEPTS)


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
