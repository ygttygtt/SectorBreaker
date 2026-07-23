"""Bounded ReAct runtime for the V3 Agent Kernel."""

from __future__ import annotations

import asyncio

from backend.app.agent_kernel.models import (
    AgentActionType,
    AgentDecision,
    KernelLoopConfig,
    KernelObservation,
    KernelRunResult,
    KernelRunStatus,
    KernelTraceEvent,
    TraceEventKind,
)
from backend.app.agent_kernel.policy import LLMAgentPolicy
from backend.app.agent_kernel.reducer import apply_state_delta
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry
from backend.app.schemas import RunEvent


class AgentKernelRuntime:
    """Execute LLM-decided actions until finish, ask-user, block, or budget stop."""

    def __init__(
        self,
        *,
        policy: LLMAgentPolicy,
        registry: ToolRegistry,
        config: KernelLoopConfig | None = None,
    ) -> None:
        self.policy = policy
        self.registry = registry
        self.config = config or KernelLoopConfig()
        self._failed_writes: list[str] = []

    async def run(self, context: KernelRuntimeContext) -> KernelRunResult:
        trace: list[KernelTraceEvent] = []
        self._failed_writes = []
        consecutive_failed_tools = 0
        for iteration in range(1, self.config.max_iterations + 1):
            decision = await self._decide_with_heartbeat(
                context=context,
                state=context.state,
                available_tools=self.registry.specs(),
                trace_tail=trace[-10:],
                loop_config=self.config,
                artifacts=context.artifacts,
            )
            user_text = (decision.user_notice or "").strip() or decision.thought_summary
            thought = KernelTraceEvent(
                kind=TraceEventKind.THOUGHT,
                message=user_text,
                data={
                    **decision.model_dump(mode="json"),
                    "user_notice": decision.user_notice,
                },
            )
            trace.append(thought)
            await self._emit(context, thought, gate="agent_decide", agent="V3 Master Agent")

            if decision.action_type == AgentActionType.FINISH:
                if not context.has_current_run_output():
                    blocked = KernelTraceEvent(
                        kind=TraceEventKind.BLOCKED,
                        message="Decision: Agent 尝试 finish，但本轮没有新产物，已阻断防止假成功。",
                        data={"stop_reason": decision.stop_reason},
                    )
                    trace.append(blocked)
                    await self._emit(context, blocked, gate="agent_decide", agent="V3 Master Agent", severity="error")
                    return self._result(KernelRunStatus.BLOCKED, context, trace, iteration, "finish_without_run_output")
                done = KernelTraceEvent(
                    kind=TraceEventKind.DECISION,
                    message=f"Decision: {decision.stop_reason}",
                    data=decision.model_dump(mode="json"),
                )
                trace.append(done)
                await self._emit(context, done, gate="export", agent="V3 Master Agent")
                return self._result(KernelRunStatus.COMPLETED, context, trace, iteration, decision.stop_reason)

            if decision.action_type == AgentActionType.BLOCK:
                blocked = KernelTraceEvent(
                    kind=TraceEventKind.BLOCKED,
                    message=f"Blocked: {decision.stop_reason}",
                    data=decision.model_dump(mode="json"),
                )
                trace.append(blocked)
                await self._emit(context, blocked, gate="agent_decide", agent="V3 Master Agent", severity="error")
                return self._result(KernelRunStatus.BLOCKED, context, trace, iteration, decision.stop_reason)

            tool_calls = self._tool_calls_for_decision(decision)
            if not tool_calls:
                observation = KernelObservation(
                    tool_name="none",
                    success=False,
                    summary="Agent 决策缺少 tool_call，无法执行。",
                    error="missing tool_call",
                )
                consecutive_failed_tools, early_result = await self._handle_observation(
                    context=context,
                    trace=trace,
                    iteration=iteration,
                    decision=decision,
                    observation=observation,
                    consecutive_failed_tools=consecutive_failed_tools,
                )
                if early_result is not None:
                    return early_result
            for tool_call in tool_calls:
                action_event = KernelTraceEvent(
                    kind=TraceEventKind.ACTION,
                    message=(decision.user_notice or "").strip() or tool_call.tool_name,
                    data={
                        **tool_call.model_dump(mode="json"),
                        "current_goal": decision.current_goal,
                        "plan_steps": decision.plan_steps,
                        "progress_check": decision.progress_check,
                        "user_notice": decision.user_notice,
                    },
                )
                trace.append(action_event)
                await self._emit(context, action_event, gate="tool_execution", agent="V3 Tool Executor")
                budget_observation = self._budget_check(tool_call, context)
                observation = budget_observation or await self.registry.dispatch(tool_call, context)
                consecutive_failed_tools, early_result = await self._handle_observation(
                    context,
                    trace=trace,
                    iteration=iteration,
                    decision=decision,
                    observation=observation,
                    consecutive_failed_tools=consecutive_failed_tools,
                )
                if early_result is not None:
                    return early_result
        return self._result(KernelRunStatus.MAX_ITERATIONS, context, trace, self.config.max_iterations, "达到最大迭代次数")

    @staticmethod
    def _tool_calls_for_decision(decision: AgentDecision):
        if decision.tool_calls:
            return decision.tool_calls
        if decision.tool_call is not None:
            return [decision.tool_call]
        return []

    def _budget_check(self, tool_call, context: KernelRuntimeContext) -> KernelObservation | None:
        name = tool_call.tool_name
        if name == "search_web" and context.search_call_count >= self.config.max_search_calls:
            return KernelObservation(
                tool_name=name,
                success=False,
                summary=f"搜索预算已用尽（{self.config.max_search_calls} 次），需要调整计划或请求用户授权。",
                error="search budget exhausted",
                requires_human=True,
            )
        writer_tools = {
            "write_layer_document",
            "revise_layer_document",
            "write_explainer_card",
            "write_explainer_cards_batch",
            "write_vault_index",
            "generate_run_narrative",
        }
        if name in writer_tools and context.writer_call_count >= self.config.max_writer_calls:
            return KernelObservation(
                tool_name=name,
                success=False,
                summary=f"写作预算已用尽（{self.config.max_writer_calls} 次），需要调整计划或请求用户授权。",
                error="writer budget exhausted",
                requires_human=True,
            )
        return None

    async def _decide_with_heartbeat(self, context: KernelRuntimeContext, **kwargs) -> AgentDecision:
        task = asyncio.create_task(self.policy.decide(**kwargs))
        waited = 0
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=10)
            if task in done:
                break
            waited += 10
            await self._emit(
                context,
                KernelTraceEvent(
                    kind=TraceEventKind.THOUGHT,
                    message=(
                        "Thought Summary: Master Agent 正在阅读当前 State、Artifact Memory "
                        f"和工具结果，判断下一步行动（已等待约 {waited} 秒）。"
                    ),
                    data={"heartbeat": True, "waited_seconds": waited},
                ),
                gate="agent_decide",
                agent="V3 Master Agent",
            )
        return await task

    async def _handle_observation(
        self,
        context: KernelRuntimeContext,
        *,
        trace: list[KernelTraceEvent],
        iteration: int,
        decision: AgentDecision,
        observation: KernelObservation,
        consecutive_failed_tools: int,
    ) -> tuple[int, KernelRunResult | None]:
        event_gate = self._gate_for_tool(observation.tool_name)
        event_severity = self._severity_for_observation(observation)
        obs_event = KernelTraceEvent(
            kind=TraceEventKind.OBSERVATION,
            message=f"Observation: {observation.summary}",
            data=observation.model_dump(mode="json"),
        )
        trace.append(obs_event)
        await self._emit(
            context,
            obs_event,
            gate=event_gate,
            agent=observation.tool_name,
            severity=event_severity,
        )

        context.state = apply_state_delta(
            context.state,
            observation.state_delta,
            decision=decision,
            observation=observation,
            known_evidence_ids={item.id for item in context.repository.list_evidence(context.project.id)},
        )
        state_event = KernelTraceEvent(
            kind=TraceEventKind.STATE_UPDATE,
            message=(
                "State Update: "
                f"sources+{len(observation.state_delta.source_memories)}, "
                f"claims+{len(observation.state_delta.claims)}, "
                f"updated_claims+{len(observation.state_delta.updated_claims)}, "
                f"questions+{len(observation.state_delta.open_questions)}, "
                f"coverage_updates+{len(observation.state_delta.coverage_updates)}, "
                f"hidden_sources+{len(observation.state_delta.hidden_source_ids)}, "
                f"deleted_sources+{len(observation.state_delta.deleted_source_ids)}, "
                f"artifacts+{len(observation.state_delta.artifact_ids)}"
            ),
            data=observation.state_delta.model_dump(mode="json"),
        )
        trace.append(state_event)
        await self._emit(context, state_event, gate="state_update", agent="V3 State Reducer")

        # Fire checkpoint callback after successful artifact write
        if observation.success and observation.artifact_ids and context.on_artifact_written is not None:
            for artifact_id in observation.artifact_ids:
                await context.on_artifact_written(artifact_id, iteration)

        optional_writers = {"write_explainer_card", "write_explainer_cards_batch", "write_vault_index", "generate_run_narrative"}
        main_writers = {"write_layer_document", "revise_layer_document"}
        if observation.tool_name in (optional_writers | main_writers) and not observation.success:
            self._failed_writes.append(observation.summary or observation.tool_name)
            severity = "warning" if observation.tool_name in optional_writers else "error"
            note = (
                "可选卡片/索引写作失败，已跳过，不影响主文档和整轮产物。"
                if observation.tool_name in optional_writers
                else "主文档写作失败，已记录；已写成的其它文档仍会保留。"
            )
            failed = KernelTraceEvent(
                kind=TraceEventKind.WARNING,
                message="Observation: " + note,
                data=observation.model_dump(mode="json"),
            )
            trace.append(failed)
            await self._emit(
                context,
                failed,
                gate="artifact_writing",
                agent="V3 Artifact Writer",
                severity=severity,
            )
            consecutive_failed_tools += 1
            if consecutive_failed_tools >= self.config.max_consecutive_failed_tools:
                return consecutive_failed_tools, self._result(
                    KernelRunStatus.MAX_ITERATIONS if context.new_artifacts() else KernelRunStatus.FAILED,
                    context,
                    trace,
                    iteration,
                    "连续写作失败过多，已停止；已写成的产物会保留。",
                )
            return consecutive_failed_tools, None
        if observation.requires_human:
            return consecutive_failed_tools, self._result(
                KernelRunStatus.WAITING_FOR_HUMAN,
                context,
                trace,
                iteration,
                observation.summary,
            )
        if observation.tool_name == "finish_run" and observation.success:
            if not context.has_current_run_output():
                return consecutive_failed_tools, self._result(
                    KernelRunStatus.BLOCKED,
                    context,
                    trace,
                    iteration,
                    "finish_without_run_output",
                )
            return consecutive_failed_tools, self._result(
                KernelRunStatus.COMPLETED,
                context,
                trace,
                iteration,
                observation.summary,
            )
        consecutive_failed_tools = 0 if observation.success else consecutive_failed_tools + 1
        if consecutive_failed_tools >= self.config.max_consecutive_failed_tools:
            return consecutive_failed_tools, self._result(
                KernelRunStatus.FAILED,
                context,
                trace,
                iteration,
                f"连续工具失败 {consecutive_failed_tools} 次，停止以避免死循环。",
            )
        return consecutive_failed_tools, None

    @staticmethod
    def _gate_for_tool(tool_name: str) -> str:
        if tool_name in {
            "write_layer_document",
            "revise_layer_document",
            "write_explainer_card",
            "write_explainer_cards_batch",
            "write_vault_index",
            "generate_run_narrative",
        }:
            return "artifact_writing"
        if tool_name == "review_artifact":
            return "artifact_review"
        if tool_name == "ask_user":
            return "human_feedback"
        return "tool_execution"

    @staticmethod
    def _severity_for_observation(observation: KernelObservation) -> str:
        if observation.success:
            return "info"
        if observation.tool_name in {"write_layer_document", "revise_layer_document"}:
            return "error"
        return "warning"

    def _result(
        self,
        status: KernelRunStatus,
        context: KernelRuntimeContext,
        trace: list[KernelTraceEvent],
        iterations: int,
        reason: str,
    ) -> KernelRunResult:
        return KernelRunResult(
            status=status,
            state_version=context.state.state_version,
            trace=trace,
            artifact_ids=[artifact.id for artifact in context.artifacts],
            stop_reason=reason,
            iterations=iterations,
            failed_writes=list(self._failed_writes),
            partial_success=bool(context.new_artifacts() and self._failed_writes),
        )

    @staticmethod
    async def _emit(
        context: KernelRuntimeContext,
        event: KernelTraceEvent,
        *,
        gate: str,
        agent: str,
        severity: str = "info",
    ) -> None:
        await context.emit_event(RunEvent(
            event_type="node_progress",
            gate=gate,
            agent=agent,
            message=event.message,
            data=event.data,
            severity=severity,
        ))
