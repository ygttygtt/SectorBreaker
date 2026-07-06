"""Bounded ReAct runtime for the V2 Agent Kernel."""

from __future__ import annotations

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

    async def run(self, context: KernelRuntimeContext) -> KernelRunResult:
        trace: list[KernelTraceEvent] = []
        consecutive_failed_tools = 0
        for iteration in range(1, self.config.max_iterations + 1):
            decision = await self.policy.decide(
                state=context.state,
                available_tools=self.registry.specs(),
                trace_tail=trace[-10:],
                loop_config=self.config,
            )
            thought = KernelTraceEvent(
                kind=TraceEventKind.THOUGHT,
                message=f"Thought Summary: {decision.thought_summary}",
                data=decision.model_dump(mode="json"),
            )
            trace.append(thought)
            await self._emit(context, thought, gate="agent_decide", agent="V2 Master Agent")

            if decision.action_type == AgentActionType.FINISH:
                if not context.artifacts:
                    blocked = KernelTraceEvent(
                        kind=TraceEventKind.BLOCKED,
                        message="Decision: Agent 尝试 finish，但当前没有任何产物，已阻断防止假成功。",
                        data={"stop_reason": decision.stop_reason},
                    )
                    trace.append(blocked)
                    await self._emit(context, blocked, gate="agent_decide", agent="V2 Master Agent", severity="error")
                    return self._result(KernelRunStatus.BLOCKED, context, trace, iteration, "finish_without_artifacts")
                done = KernelTraceEvent(
                    kind=TraceEventKind.DECISION,
                    message=f"Decision: {decision.stop_reason}",
                    data=decision.model_dump(mode="json"),
                )
                trace.append(done)
                await self._emit(context, done, gate="export", agent="V2 Master Agent")
                return self._result(KernelRunStatus.COMPLETED, context, trace, iteration, decision.stop_reason)

            if decision.action_type == AgentActionType.BLOCK:
                blocked = KernelTraceEvent(
                    kind=TraceEventKind.BLOCKED,
                    message=f"Blocked: {decision.stop_reason}",
                    data=decision.model_dump(mode="json"),
                )
                trace.append(blocked)
                await self._emit(context, blocked, gate="agent_decide", agent="V2 Master Agent", severity="error")
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
                    message=f"Action: {tool_call.tool_name} - {tool_call.reason}",
                    data={
                        **tool_call.model_dump(mode="json"),
                        "current_goal": decision.current_goal,
                        "plan_steps": decision.plan_steps,
                        "progress_check": decision.progress_check,
                    },
                )
                trace.append(action_event)
                await self._emit(context, action_event, gate="tool_execution", agent="V2 Tool Executor")
                budget_observation = self._budget_check(tool_call)
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

    def _budget_check(self, tool_call) -> KernelObservation | None:
        name = tool_call.tool_name
        return None

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
        await self._emit(context, state_event, gate="state_update", agent="V2 State Reducer")

        if observation.tool_name == "write_layer_document" and not observation.success:
            failed = KernelTraceEvent(
                kind=TraceEventKind.BLOCKED,
                message="Blocked: LLM 写作失败，已停止运行，未导出模板或假产物。",
                data=observation.model_dump(mode="json"),
            )
            trace.append(failed)
            await self._emit(
                context,
                failed,
                gate="artifact_writing",
                agent="V2 Artifact Writer",
                severity="error",
            )
            return consecutive_failed_tools, self._result(
                KernelRunStatus.FAILED,
                context,
                trace,
                iteration,
                "artifact_writing_failed",
            )
        if observation.requires_human:
            return consecutive_failed_tools, self._result(
                KernelRunStatus.WAITING_FOR_HUMAN,
                context,
                trace,
                iteration,
                observation.summary,
            )
        if observation.tool_name == "finish_run" and observation.success:
            if not context.artifacts:
                return consecutive_failed_tools, self._result(
                    KernelRunStatus.BLOCKED,
                    context,
                    trace,
                    iteration,
                    "finish_without_artifacts",
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
        if tool_name == "write_layer_document":
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
        if observation.tool_name == "write_layer_document":
            return "error"
        return "warning"

    @staticmethod
    def _result(
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
