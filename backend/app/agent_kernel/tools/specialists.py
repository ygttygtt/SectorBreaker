"""Dynamic, scoped specialist delegation tool."""

import asyncio
import json

from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta, ToolSpec
from backend.app.agent_kernel.specialists import SpecialistResult, SpecialistTask
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema
from backend.app.providers.interfaces import ChatMessage


def register_specialist_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="delegate_specialists",
            description=(
                "Delegate up to four independent scoped tasks to registered specialist Agents. "
                "Specialists return typed findings or change suggestions and cannot apply changes."
            ),
            args_schema=schema({
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": [
                                "vault_auditor", "researcher", "verifier", "knowledge_editor",
                            ]},
                            "objective": {"type": "string"},
                            "target_paths": {"type": "array", "items": {"type": "string"}},
                            "questions": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["role", "objective"],
                    },
                    "maxItems": 4,
                },
            }, required=["tasks"]),
        ),
        delegate_specialists,
    )


async def delegate_specialists(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    if context.llm_provider is None:
        return KernelObservation(
            tool_name="delegate_specialists",
            success=False,
            summary="无法委派 Specialist：未配置 LLM Provider。",
            error="llm provider not configured",
        )
    raw_tasks = tool_call.args.get("tasks") or []
    if not isinstance(raw_tasks, list) or not raw_tasks or len(raw_tasks) > 4:
        return KernelObservation(
            tool_name="delegate_specialists",
            success=False,
            summary="Specialist 委派需要 1-4 个结构化任务。",
            error="invalid specialist task count",
        )
    try:
        tasks = [SpecialistTask.model_validate(item) for item in raw_tasks]
    except Exception as exc:
        return KernelObservation(
            tool_name="delegate_specialists",
            success=False,
            summary="Specialist 任务合同校验失败。",
            error=str(exc)[:400],
        )

    async def run_one(task: SpecialistTask) -> SpecialistResult:
        target_artifacts = [
            {
                "id": artifact.id,
                "path": artifact.content_path,
                "title": artifact.title,
                "revision": artifact.revision,
                "content": artifact.content[:5000],
                "evidence_ids": artifact.source_evidence_ids,
            }
            for artifact in context.artifacts
            if not task.target_paths or artifact.content_path in task.target_paths
        ][:8]
        prompt = (
            "你是 SectorBreaker 的任务型 Specialist Agent。你没有文件写入权，也不能直接调用外部服务。\n"
            "只分析给定上下文并返回 SpecialistResult JSON。需要进一步检索时，只能写入 recommended_tool_calls，"
            "由 Master Agent 决定是否执行。knowledge_editor 只能返回 proposed_change 建议，不能声称已经应用。\n\n"
            f"角色：{task.role.value}\n目标：{task.objective}\n"
            f"目标路径：{json.dumps(task.target_paths, ensure_ascii=False)}\n"
            f"问题：{json.dumps(task.questions, ensure_ascii=False)}\n"
            f"维护任务：{json.dumps(context.state.maintenance_task_summaries, ensure_ascii=False)}\n"
            f"相关知识：{json.dumps(target_artifacts, ensure_ascii=False)}\n"
            f"已有证据 IDs：{json.dumps(context.state.evidence_refs[-40:], ensure_ascii=False)}"
        )
        result = await context.llm_provider.complete_structured(
            [ChatMessage(role="user", content=prompt)],
            SpecialistResult,
        )
        if result.role != task.role:
            result.role = task.role
        return result

    results = await asyncio.gather(*(run_one(task) for task in tasks), return_exceptions=True)
    completed: list[SpecialistResult] = []
    failures: list[str] = []
    for task, result in zip(tasks, results, strict=True):
        if isinstance(result, Exception):
            failures.append(f"{task.role.value}: {type(result).__name__}: {str(result)[:180]}")
        else:
            completed.append(result)
    notes = [f"{result.role.value} | {result.objective} | {result.summary}" for result in completed]
    return KernelObservation(
        tool_name="delegate_specialists",
        success=bool(completed),
        summary=f"完成 {len(completed)} 个 Specialist 任务，失败 {len(failures)} 个。",
        data={
            "results": [result.model_dump(mode="json") for result in completed],
            "failures": failures,
        },
        state_delta=KernelStateDelta(delegation_notes=notes),
        error="; ".join(failures) if failures and not completed else None,
    )
