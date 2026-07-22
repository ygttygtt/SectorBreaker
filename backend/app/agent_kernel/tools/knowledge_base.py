"""Knowledge health, maintenance backlog, and ChangeSet tools."""

from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta, ToolSpec
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema
from backend.app.knowledge_base import ChangeSetService, VaultKnowledgeService
from backend.app.schemas import ChangeSetProposalRequest


def register_knowledge_base_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="inspect_vault_health",
            description="Read or generate the deterministic knowledge-health report for the managed vault.",
            args_schema=schema({"refresh": {"type": "boolean"}}),
        ),
        inspect_vault_health,
    )
    registry.register(
        ToolSpec(
            name="inspect_maintenance_backlog",
            description="Read persistent maintenance tasks and their target paths/status.",
            args_schema=schema({
                "status": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            }),
        ),
        inspect_maintenance_backlog,
    )
    registry.register(
        ToolSpec(
            name="propose_change_set",
            description=(
                "Propose one safe Markdown create/update ChangeSet with a base hash and unified diff. "
                "Only apply_safe operations allowed by AutonomyPolicy may be applied automatically; "
                "all other changes wait for review."
            ),
            args_schema=schema({
                "task_id": {"type": "string"},
                "summary": {"type": "string"},
                "path": {"type": "string"},
                "after_content": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "factual_change": {"type": "boolean"},
            }, required=["summary", "path", "after_content"]),
        ),
        propose_change_set,
    )


async def inspect_vault_health(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    service = VaultKnowledgeService(context.repository)
    refresh = bool(tool_call.args.get("refresh", False))
    report = service.audit(context.project.id) if refresh else context.repository.latest_health_report(context.project.id)
    if report is None:
        report = service.audit(context.project.id)
    context.state.latest_health_report_id = report.id
    return KernelObservation(
        tool_name="inspect_vault_health",
        success=True,
        summary=f"知识健康报告包含 {len(report.findings)} 个发现。",
        data=report.model_dump(mode="json"),
        state_delta=KernelStateDelta(
            task_notes=[f"health:{item.finding_type.value}:{','.join(item.target_paths)}" for item in report.findings[:30]],
        ),
    )


async def inspect_maintenance_backlog(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    status = str(tool_call.args.get("status") or "").strip()
    limit = max(1, min(int(tool_call.args.get("limit") or 30), 100))
    tasks = context.repository.list_maintenance_tasks(context.project.id)
    if status:
        tasks = [task for task in tasks if task.status.value == status]
    tasks = tasks[:limit]
    context.state.maintenance_task_ids = [task.id for task in tasks]
    context.state.maintenance_task_summaries = [
        f"{task.id} | {task.task_type} | {task.objective} | paths={','.join(task.target_paths)}"
        for task in tasks
    ]
    return KernelObservation(
        tool_name="inspect_maintenance_backlog",
        success=True,
        summary=f"读取维护任务 {len(tasks)} 个。",
        data={"tasks": [task.model_dump(mode="json") for task in tasks]},
    )


async def propose_change_set(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    try:
        request = ChangeSetProposalRequest(
            task_id=str(tool_call.args.get("task_id") or "").strip() or None,
            summary=str(tool_call.args.get("summary") or "").strip(),
            path=str(tool_call.args.get("path") or "").strip(),
            after_content=str(tool_call.args.get("after_content") or "").strip(),
            evidence_ids=[str(item) for item in tool_call.args.get("evidence_ids") or []],
            factual_change=bool(tool_call.args.get("factual_change", False)),
        )
        change_set = ChangeSetService(context.repository).propose(
            context.project.id,
            request,
            actor="master_agent",
            run_id=context.run_id,
        )
    except Exception as exc:
        return KernelObservation(
            tool_name="propose_change_set",
            success=False,
            summary="ChangeSet 提案失败。",
            error=f"{type(exc).__name__}: {str(exc)[:300]}",
        )
    policy = context.state.autonomy_policy
    can_auto_apply = policy.execution_mode == "apply_safe" and all(
        (
            operation.operation.value == "create"
            and policy.allow_create
            and _path_allowed(operation.path, policy.allowed_write_prefixes)
        )
        or (
            operation.operation.value == "update"
            and policy.allow_update
            and _path_allowed(operation.path, policy.allowed_write_prefixes)
        )
        for operation in change_set.operations
    )
    if can_auto_apply:
        try:
            service = ChangeSetService(context.repository)
            service.approve(change_set.id)
            applied = service.apply(change_set.id, policy=policy)
            if applied.status.value == "applied":
                applied_artifacts = [
                    context.repository.get_artifact(artifact_id)
                    for artifact_id in applied.applied_artifact_ids
                ]
                known_ids = {artifact.id for artifact in context.artifacts}
                context.artifacts.extend(
                    artifact for artifact in applied_artifacts if artifact.id not in known_ids
                )
                summary = f"ChangeSet 已按 apply_safe 策略应用：{applied.id}。"
                return KernelObservation(
                    tool_name="propose_change_set",
                    success=True,
                    summary=summary,
                    data=applied.model_dump(mode="json"),
                    state_delta=KernelStateDelta(
                        artifact_ids=applied.applied_artifact_ids,
                        task_notes=[summary],
                    ),
                    artifact_ids=applied.applied_artifact_ids,
                )
            change_set = applied
        except Exception as exc:
            return KernelObservation(
                tool_name="propose_change_set",
                success=False,
                summary="ChangeSet 自动应用失败，未绕过安全边界。",
                error=f"{type(exc).__name__}: {str(exc)[:300]}",
            )
    return KernelObservation(
        tool_name="propose_change_set",
        success=True,
        summary=f"已生成待审查 ChangeSet：{change_set.id}，尚未应用。",
        data=change_set.model_dump(mode="json"),
        requires_human=True,
    )


def _path_allowed(path: str, prefixes: list[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    return any(
        not prefix or normalized.startswith(prefix.replace("\\", "/").lstrip("/"))
        for prefix in prefixes
    )
