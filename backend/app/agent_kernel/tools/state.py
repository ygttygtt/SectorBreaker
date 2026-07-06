"""State-update tools for the V2 Agent Kernel."""

from __future__ import annotations

from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta, ToolSpec
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema
from backend.app.agent_state.models import CoverageStatus, KnowledgeClaim, OpenQuestion


def register_state_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="internalize_observation",
            description="Convert a recent observation into open questions, task notes, and structured memory hints.",
            args_schema=schema({
                "summary": {"type": "string"},
                "open_questions": {"type": "array", "items": {"type": "string"}},
                "coverage_gaps": {"type": "array", "items": {"type": "string"}},
                "drill_down_tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "concept_or_entity": {"type": "string"},
                            "parent_layer_id": {"type": "string"},
                            "priority": {"type": "integer"},
                            "reason": {"type": "string"},
                            "suggested_actions": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            }),
        ),
        internalize_observation,
    )
    registry.register(
        ToolSpec(
            name="update_task_state",
            description="Record local task progress, reflections, and next missing dimensions without polluting shared knowledge.",
            args_schema=schema({
                "note": {"type": "string"},
                "coverage_gaps": {"type": "array", "items": {"type": "string"}},
            }, required=["note"]),
        ),
        update_task_state,
    )
    registry.register(
        ToolSpec(
            name="evaluate_coverage",
            description="Evaluate whether the current or specified knowledge layer has enough evidence, claims, and resolved questions to write.",
            args_schema=schema({
                "layer_id": {"type": "string"},
                "notes": {"type": "string"},
            }),
        ),
        evaluate_coverage,
    )
    registry.register(
        ToolSpec(
            name="reflect_on_progress",
            description="Reflect on recent attempts, failed searches, current gaps, and adjust the next research strategy.",
            args_schema=schema({
                "reflection": {"type": "string"},
                "coverage_gaps": {"type": "array", "items": {"type": "string"}},
                "next_steps": {"type": "array", "items": {"type": "string"}},
            }, required=["reflection"]),
        ),
        reflect_on_progress,
    )
    registry.register(
        ToolSpec(
            name="manage_state_memory",
            description="Hide, delete, supersede, resolve, or lightly update state memories after the Agent identifies noise, outdated claims, or resolved questions.",
            args_schema=schema({
                "hidden_source_ids": {"type": "array", "items": {"type": "string"}},
                "deleted_source_ids": {"type": "array", "items": {"type": "string"}},
                "hidden_claim_ids": {"type": "array", "items": {"type": "string"}},
                "deleted_claim_ids": {"type": "array", "items": {"type": "string"}},
                "superseded_claim_ids": {"type": "array", "items": {"type": "string"}},
                "resolved_open_question_ids": {"type": "array", "items": {"type": "string"}},
                "claim_updates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "text": {"type": "string"},
                            "verification_status": {"type": "string"},
                            "confidence": {"type": "number"},
                            "revision_reason": {"type": "string"},
                        },
                    },
                },
                "reason": {"type": "string"},
            }),
        ),
        manage_state_memory,
    )


async def internalize_observation(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    summary = str(tool_call.args.get("summary") or "").strip()
    raw_questions = tool_call.args.get("open_questions") or []
    raw_gaps = tool_call.args.get("coverage_gaps") or []
    raw_drill_down_tasks = tool_call.args.get("drill_down_tasks") or []
    layer_ids = [context.state.current_layer_id] if context.state.current_layer_id else []
    questions = [
        OpenQuestion(
            question=str(question),
            layer_ids=layer_ids,
            reason=summary or "Agent Kernel 内化观察时标记的待验证问题。",
            suggested_actions=["继续搜索", "读取上传报告", "检索项目记忆", "人工核验"],
        )
        for question in raw_questions
        if str(question).strip()
    ]
    for item in raw_drill_down_tasks:
        if not isinstance(item, dict):
            continue
        question_text = str(item.get("question") or "").strip()
        if not question_text:
            continue
        parent_layer_id = str(item.get("parent_layer_id") or context.state.current_layer_id or "").strip()
        task_layer_ids = [parent_layer_id] if parent_layer_id else layer_ids
        questions.append(OpenQuestion(
            question=question_text,
            layer_ids=task_layer_ids,
            parent_layer_id=parent_layer_id or None,
            concept_or_entity=str(item.get("concept_or_entity") or "").strip(),
            reason=str(item.get("reason") or summary or "Agent 发现复杂概念，需要下钻。").strip(),
            priority=_safe_priority(item.get("priority")),
            suggested_actions=[
                str(action) for action in (item.get("suggested_actions") or ["继续搜索", "生成概念卡片"])
                if str(action).strip()
            ],
            status="drill_down",
        ))
    delta = KernelStateDelta(
        open_questions=questions,
        task_notes=[summary] if summary else [],
        coverage_gaps=[str(item) for item in raw_gaps if str(item).strip()],
    )
    return KernelObservation(
        tool_name="internalize_observation",
        success=True,
        summary=f"已内化观察：新增 {len(questions)} 个待验证问题，记录 {len(delta.coverage_gaps)} 个覆盖缺口。",
        data={
            "summary": summary,
            "open_questions": raw_questions,
            "coverage_gaps": raw_gaps,
            "drill_down_tasks": raw_drill_down_tasks,
        },
        state_delta=delta,
    )


async def update_task_state(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    note = str(tool_call.args.get("note") or "").strip()
    gaps = [str(item) for item in (tool_call.args.get("coverage_gaps") or []) if str(item).strip()]
    delta = KernelStateDelta(task_notes=[note] if note else [], coverage_gaps=gaps)
    return KernelObservation(
        tool_name="update_task_state",
        success=bool(note or gaps),
        summary=f"已更新任务状态：{note or '无备注'}" + (f"；缺口：{'；'.join(gaps)}" if gaps else ""),
        data={"note": note, "coverage_gaps": gaps},
        state_delta=delta,
    )


async def evaluate_coverage(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    layer_id = str(tool_call.args.get("layer_id") or context.state.current_layer_id or "").strip()
    layer = context.state.knowledge_schema.layer(layer_id) if layer_id else None
    if layer is None:
        return KernelObservation(
            tool_name="evaluate_coverage",
            success=False,
            summary=f"无法评估覆盖度：未知 layer_id={layer_id or '未指定'}",
            error="unknown layer",
        )

    layer_key = _layer_value(layer.id)
    evidence_ids = set()
    claim_count = 0
    verified_claim_count = 0
    for claim in context.state.shared_knowledge.claims:
        if layer_key not in {_layer_value(item) for item in claim.layer_ids}:
            continue
        if not claim.active or claim.hidden_from_context or claim.superseded_by:
            continue
        claim_count += 1
        evidence_ids.update(claim.evidence_ids)
        if claim.verification_status in {"verified", "partially_verified"}:
            verified_claim_count += 1
    source_count = sum(
        1
        for source in context.state.shared_knowledge.source_memories
        if source.active
        and not source.hidden_from_context
        and (not source.related_layer_ids or layer_key in {_layer_value(item) for item in source.related_layer_ids})
    )
    open_questions = [
        question for question in context.state.shared_knowledge.open_questions
        if not question.resolved and layer_key in {_layer_value(item) for item in question.layer_ids}
    ]
    criteria_count = max(len(layer.completion_criteria), 1)
    evidence_score = min(1.0, len(evidence_ids) / max(criteria_count * 2, 2))
    claim_score = min(1.0, claim_count / max(criteria_count, 1))
    verification_score = min(1.0, verified_claim_count / max(claim_count, 1)) if claim_count else 0.0
    question_penalty = min(0.35, len(open_questions) * 0.08)
    score = max(0.0, min(1.0, evidence_score * 0.35 + claim_score * 0.3 + verification_score * 0.25 + min(1.0, source_count / 4) * 0.1 - question_penalty))
    source_policy = context.project.source_policy.value
    enough_partial_material = len(evidence_ids) >= 5 and claim_count >= 5 and source_count >= 4
    partial_threshold = 0.32 if source_policy == "open_web" else 0.35
    if score >= 0.72 and len(open_questions) <= 1:
        status = CoverageStatus.SUFFICIENT
    elif score >= 0.48 or (score >= partial_threshold and enough_partial_material):
        status = CoverageStatus.DEGRADED
    else:
        status = CoverageStatus.NEEDS_MORE
    ready_to_write = status in {CoverageStatus.SUFFICIENT, CoverageStatus.DEGRADED} and claim_count > 0
    notes = str(tool_call.args.get("notes") or "").strip()
    coverage_notes = (
        f"score={score:.2f}; evidence={len(evidence_ids)}; claims={claim_count}; "
        f"verified_or_partial={verified_claim_count}; open_questions={len(open_questions)}. "
        f"source_policy={source_policy}; partial_material_ready={enough_partial_material}; "
        f"{notes}"
    ).strip()
    delta = KernelStateDelta(
        coverage_gaps=[question.question for question in open_questions],
        coverage_updates=[{
            "layer_id": layer_key,
            "coverage_score": score,
            "coverage_status": status.value,
            "coverage_notes": coverage_notes,
            "ready_to_write": ready_to_write,
            "evidence_count": len(evidence_ids),
            "claim_count": claim_count,
            "open_question_count": len(open_questions),
        }],
    )
    return KernelObservation(
        tool_name="evaluate_coverage",
        success=True,
        summary=f"覆盖评估：{layer.title} score={score:.2f} status={status.value} ready_to_write={ready_to_write}",
        data={
            "layer_id": layer_key,
            "coverage_score": score,
            "coverage_status": status.value,
            "ready_to_write": ready_to_write,
            "evidence_count": len(evidence_ids),
            "claim_count": claim_count,
            "open_question_count": len(open_questions),
        },
        state_delta=delta,
    )


async def reflect_on_progress(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    reflection = str(tool_call.args.get("reflection") or "").strip()
    gaps = [str(item) for item in (tool_call.args.get("coverage_gaps") or []) if str(item).strip()]
    next_steps = [str(item) for item in (tool_call.args.get("next_steps") or []) if str(item).strip()]
    current_task = context.state.working_memory.get(context.state.current_task_id or "") if context.state.current_task_id else None
    if current_task is not None:
        current_task.local_reflections.append(reflection)
        current_task.memory_summary = "；".join([current_task.memory_summary, reflection]).strip("；")[-1000:]
        current_task.checklist = list(dict.fromkeys(current_task.checklist + next_steps))
    delta = KernelStateDelta(
        task_notes=[reflection],
        coverage_gaps=gaps,
        phase_reflection=reflection,
    )
    return KernelObservation(
        tool_name="reflect_on_progress",
        success=bool(reflection),
        summary=f"阶段反思：{reflection[:220]}" + (f"；下一步：{'；'.join(next_steps[:3])}" if next_steps else ""),
        data={"reflection": reflection, "coverage_gaps": gaps, "next_steps": next_steps},
        state_delta=delta,
    )


async def manage_state_memory(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    reason = str(tool_call.args.get("reason") or "").strip()
    claim_updates = _build_claim_updates(tool_call.args.get("claim_updates") or [], context)
    delta = KernelStateDelta(
        updated_claims=claim_updates,
        hidden_source_ids=_string_list(tool_call.args.get("hidden_source_ids")),
        deleted_source_ids=_string_list(tool_call.args.get("deleted_source_ids")),
        hidden_claim_ids=_string_list(tool_call.args.get("hidden_claim_ids")),
        deleted_claim_ids=_string_list(tool_call.args.get("deleted_claim_ids")),
        superseded_claim_ids=_string_list(tool_call.args.get("superseded_claim_ids")),
        resolved_open_question_ids=_string_list(tool_call.args.get("resolved_open_question_ids")),
        task_notes=[reason] if reason else [],
        phase_reflection=reason,
    )
    changed_count = (
        len(delta.updated_claims)
        + len(delta.hidden_source_ids)
        + len(delta.deleted_source_ids)
        + len(delta.hidden_claim_ids)
        + len(delta.deleted_claim_ids)
        + len(delta.superseded_claim_ids)
        + len(delta.resolved_open_question_ids)
    )
    return KernelObservation(
        tool_name="manage_state_memory",
        success=changed_count > 0,
        summary=f"状态记忆治理完成：{changed_count} 项变更。" + (f" 原因：{reason}" if reason else ""),
        data={
            "changed_count": changed_count,
            "reason": reason,
            "claim_updates": [claim.model_dump(mode="json") for claim in claim_updates],
        },
        state_delta=delta,
    )


def _layer_value(layer_id) -> str:
    return layer_id.value if hasattr(layer_id, "value") else str(layer_id)


def _safe_priority(value) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 3


def _string_list(value) -> list[str]:
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def _build_claim_updates(raw_updates, context: KernelRuntimeContext) -> list[KnowledgeClaim]:
    existing = {claim.id: claim for claim in context.state.shared_knowledge.claims}
    updates: list[KnowledgeClaim] = []
    for item in raw_updates:
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("id") or "").strip()
        if not claim_id or claim_id not in existing:
            continue
        original = existing[claim_id]
        updates.append(original.model_copy(update={
            "text": str(item.get("text") or original.text).strip(),
            "verification_status": str(item.get("verification_status") or original.verification_status).strip(),
            "confidence": _safe_confidence(item.get("confidence"), original.confidence),
            "revision_reason": str(item.get("revision_reason") or item.get("reason") or original.revision_reason).strip(),
        }))
    return updates


def _safe_confidence(value, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default
