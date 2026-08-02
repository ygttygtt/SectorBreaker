"""LLM mission planning constrained by a typed task grammar."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.providers.interfaces import ChatMessage, LLMProvider
from backend.app.schemas import (
    AgentMission,
    LiveChallengeRequest,
    TaskBudget,
    WorkOrder,
    WorkOrderType,
)


ALLOWED_CAPABILITIES = {
    "research_foundations",
    "research_ecosystem",
    "verify_claims",
    "counterevidence",
    "synthesize_starter_note",
    "propose_change_set",
}


class PlannedWorkOrder(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$")
    task_type: Literal["research", "verify", "edit"]
    objective: str
    research_angle: str = ""
    required_capabilities: list[str]
    depends_on: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    optional: bool = False

    @field_validator("required_capabilities", "depends_on", "acceptance_criteria", mode="before")
    @classmethod
    def normalize_scalar_lists(cls, value):
        """Repair a common JSON-mode shape without accepting free-form data."""

        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class MissionPlanDraft(BaseModel):
    objective: str
    planning_reason: str
    tasks: list[PlannedWorkOrder]

    @model_validator(mode="after")
    def validate_task_grammar(self) -> "MissionPlanDraft":
        if not 4 <= len(self.tasks) <= 6:
            raise ValueError("live challenge plan requires 4-6 tasks")
        keys = [task.key for task in self.tasks]
        if len(keys) != len(set(keys)):
            raise ValueError("planned task keys must be unique")
        known = set(keys)
        for task in self.tasks:
            if set(task.required_capabilities) - ALLOWED_CAPABILITIES:
                raise ValueError("planned task uses unregistered capabilities")
            if set(task.depends_on) - known:
                raise ValueError("planned task references unknown dependency")
            allowed_for_type = {
                "research": {"research_foundations", "research_ecosystem"},
                "verify": {"verify_claims", "counterevidence"},
                "edit": {"synthesize_starter_note", "propose_change_set"},
            }[task.task_type]
            if not task.required_capabilities or set(task.required_capabilities) - allowed_for_type:
                raise ValueError("planned task capabilities do not match its task type")
        research = [task for task in self.tasks if task.task_type == "research"]
        verify = [task for task in self.tasks if task.task_type == "verify"]
        edit = [task for task in self.tasks if task.task_type == "edit"]
        if not 2 <= len(research) <= 3 or len(verify) != 1 or len(edit) != 1:
            raise ValueError("plan requires two or three research tasks, one verifier, and one editor")
        research_capabilities = [set(task.required_capabilities) for task in research]
        if any(len(item) != 1 for item in research_capabilities):
            raise ValueError("each research task requires exactly one specialist capability")
        foundation_count = sum(item == {"research_foundations"} for item in research_capabilities)
        ecosystem_count = sum(item == {"research_ecosystem"} for item in research_capabilities)
        if foundation_count != 1 or not 1 <= ecosystem_count <= 2:
            raise ValueError("plan requires one foundation and one or two ecosystem research tasks")
        if any(task.depends_on for task in research):
            raise ValueError("live research tasks must start independently")
        required_research_keys = {task.key for task in research if not task.optional}
        if set(verify[0].depends_on) != required_research_keys:
            raise ValueError("verifier must depend on every required research task")
        if set(edit[0].depends_on) != {verify[0].key}:
            raise ValueError("editor must depend exactly on the verifier")
        return self


async def plan_live_challenge(
    *,
    project_id: str,
    run_id: str,
    request: LiveChallengeRequest,
    llm_provider: LLMProvider,
) -> AgentMission:
    default_goal = (
        f"形成“{request.domain}”的入门地图、核心概念、关键参与者、运行机制、"
        "一个重要争议，以及后续研究问题。"
    )
    objective = (request.question or "").strip() or default_goal
    prompt = f"""
你是 SectorBreaker Master Agent 的 Mission Planner。为一个 5 分钟现场挑战生成动态任务图。
领域：{request.domain}
用户目标：{objective}

只能使用 research / verify / edit 三种任务，能力只能来自：
- research_foundations
- research_ecosystem
- verify_claims
- counterevidence
- synthesize_starter_note
- propose_change_set

必须满足：
1. 4-5 个任务：恰好一个 foundation research，以及一到两个 ecosystem research；所有 research 互不依赖；
2. research 的研究角度不能重复；
3. 恰好一个 verify，依赖所有必需 research；
4. 恰好一个 edit，依赖 verify；
5. 每项写出可检查的 acceptance_criteria；
6. 不把固定 L1-L5 当执行顺序；根据这个领域选择具体研究角度；
7. 返回 MissionPlanDraft JSON，不输出解释性散文。
""".strip()
    draft = await llm_provider.complete_structured(
        [ChatMessage(role="user", content=prompt)],
        MissionPlanDraft,
    )
    planned_tasks = list(draft.tasks)
    if request.deadline_seconds <= 300:
        # The five-minute contract owns two concurrent research slots. Longer
        # challenges may keep the optional second ecosystem angle.
        foundation = next(task for task in planned_tasks if task.task_type == "research" and "research_foundations" in task.required_capabilities)
        ecosystem = next(task for task in planned_tasks if task.task_type == "research" and "research_ecosystem" in task.required_capabilities)
        verifier = next(task for task in planned_tasks if task.task_type == "verify")
        editor = next(task for task in planned_tasks if task.task_type == "edit")
        verifier = verifier.model_copy(update={"depends_on": [foundation.key, ecosystem.key]})
        editor = editor.model_copy(update={"depends_on": [verifier.key]})
        planned_tasks = [foundation, ecosystem, verifier, editor]
    mission_id = f"MISSION-{run_id.removeprefix('run-')[:12]}"
    id_by_key = {task.key: f"WO-{run_id.removeprefix('run-')[:6]}-{index + 1}" for index, task in enumerate(planned_tasks)}
    work_orders: list[WorkOrder] = []
    for task in planned_tasks:
        task_type = WorkOrderType(task.task_type)
        budget = TaskBudget(
            max_steps=3,
            max_search_calls=1 if task_type in {WorkOrderType.RESEARCH, WorkOrderType.VERIFY} else 0,
            max_provider_requests=4 if task_type in {WorkOrderType.RESEARCH, WorkOrderType.VERIFY} else 0,
            max_extraction_requests=3 if task_type in {WorkOrderType.RESEARCH, WorkOrderType.VERIFY} else 0,
            max_llm_calls=3 if task_type != WorkOrderType.EDIT else 2,
            deadline_seconds=120 if task_type == WorkOrderType.RESEARCH else 90,
        )
        work_orders.append(WorkOrder(
            id=id_by_key[task.key],
            mission_id=mission_id,
            task_type=task_type,
            objective=task.objective,
            research_angle=task.research_angle,
            required_capabilities=task.required_capabilities,
            depends_on=[id_by_key[key] for key in task.depends_on],
            acceptance_criteria=task.acceptance_criteria,
            budget=budget,
            optional=task.optional,
        ))
    started_at = datetime.now(UTC)
    return AgentMission(
        id=mission_id,
        run_id=run_id,
        project_id=project_id,
        domain=request.domain,
        objective=objective,
        deadline_seconds=request.deadline_seconds,
        started_at=started_at,
        deadline_at=started_at + timedelta(seconds=request.deadline_seconds),
        work_orders=work_orders,
    )
