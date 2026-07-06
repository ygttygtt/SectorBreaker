"""State-update tools for the V2 Agent Kernel."""

from __future__ import annotations

from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta, ToolSpec
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema
from backend.app.agent_state.models import OpenQuestion


def register_state_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="internalize_observation",
            description="Convert a recent observation into open questions, task notes, and structured memory hints.",
            args_schema=schema({
                "summary": {"type": "string"},
                "open_questions": {"type": "array", "items": {"type": "string"}},
                "coverage_gaps": {"type": "array", "items": {"type": "string"}},
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


async def internalize_observation(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    summary = str(tool_call.args.get("summary") or "").strip()
    raw_questions = tool_call.args.get("open_questions") or []
    raw_gaps = tool_call.args.get("coverage_gaps") or []
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
    delta = KernelStateDelta(
        open_questions=questions,
        task_notes=[summary] if summary else [],
        coverage_gaps=[str(item) for item in raw_gaps if str(item).strip()],
    )
    return KernelObservation(
        tool_name="internalize_observation",
        success=True,
        summary=f"已内化观察：新增 {len(questions)} 个待验证问题，记录 {len(delta.coverage_gaps)} 个覆盖缺口。",
        data={"summary": summary, "open_questions": raw_questions, "coverage_gaps": raw_gaps},
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
