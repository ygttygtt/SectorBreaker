"""LLM policy for the V2 Agent Kernel."""

from __future__ import annotations

from pathlib import Path

from backend.app.agent_kernel.context import KernelContextBuilder
from backend.app.agent_kernel.models import (
    AgentActionType,
    AgentDecision,
    KernelLoopConfig,
    KernelTraceEvent,
    ToolCall,
    ToolSpec,
)
from backend.app.agent_state.models import SectorBreakerState
from backend.app.providers.interfaces import ChatMessage, LLMProvider


class LLMAgentPolicy:
    """Ask the LLM to choose the next tool/action from State."""

    def __init__(self, llm_provider: LLMProvider | None) -> None:
        self.llm_provider = llm_provider
        self.context_builder = KernelContextBuilder()

    async def decide(
        self,
        *,
        state: SectorBreakerState,
        available_tools: list[ToolSpec],
        trace_tail: list[KernelTraceEvent],
        loop_config: KernelLoopConfig,
    ) -> AgentDecision:
        if self.llm_provider is None:
            return AgentDecision(
                thought_summary="当前没有配置 LLM，无法执行真正的 Agent 决策。",
                action_type=AgentActionType.BLOCK,
                stop_reason="LLM provider not configured",
            )
        prompt = self._build_prompt(
            state=state,
            available_tools=available_tools,
            trace_tail=trace_tail,
            loop_config=loop_config,
        )
        try:
            decision = await self.llm_provider.complete_structured(
                [ChatMessage(role="user", content=prompt)],
                AgentDecision,
            )
        except Exception as exc:
            return AgentDecision(
                thought_summary=f"上一轮 LLM 决策输出无法解析，需要记录错误并进入自我修正。错误：{type(exc).__name__}",
                action_type=AgentActionType.CALL_TOOL,
                tool_call=ToolCall(
                    tool_name="update_task_state",
                    args={"note": f"LLM decision invalid: {type(exc).__name__}: {str(exc)[:220]}"},
                    reason="保持 Agent loop 可观察，不静默降级成固定 workflow。",
                ),
                expected_observation="记录格式错误并进入下一轮决策。",
            )
        return decision

    def _build_prompt(
        self,
        *,
        state: SectorBreakerState,
        available_tools: list[ToolSpec],
        trace_tail: list[KernelTraceEvent],
        loop_config: KernelLoopConfig,
    ) -> str:
        context = self.context_builder.build_prompt_context(
            state=state,
            tools=available_tools,
            trace_tail=trace_tail,
        )
        prompt_parts = [
            load_prompt("master_agent_system.md"),
            load_prompt("state_reader.md"),
            load_prompt("tool_decision.md"),
            load_prompt("search_strategy.md"),
            load_prompt("coverage_judge.md"),
            "# Runtime Budget\n"
            f"- max_iterations: {loop_config.max_iterations}\n"
            f"- max_search_calls: {loop_config.max_search_calls}\n"
            f"- max_writer_calls: {loop_config.max_writer_calls}\n"
            f"- max_consecutive_failed_tools: {loop_config.max_consecutive_failed_tools}\n",
            "# Current State And Tools\n" + context,
            "# Required Output\n"
            "只返回一个 JSON 对象，必须符合 AgentDecision schema。"
            "不要输出 Markdown，不要解释 JSON 之外的文字。"
            "如果要写文档，action_type 使用 write_artifact，tool_call.tool_name 使用 write_layer_document。"
            "如果要审查文档，action_type 使用 review_artifact，tool_call.tool_name 使用 review_artifact。"
            "如果认为完成，action_type 使用 finish 且给出 stop_reason。"
        ]
        return "\n\n".join(prompt_parts)


def load_prompt(name: str) -> str:
    path = Path(__file__).parents[1] / "agents" / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        f"# Missing Prompt: {name}\n"
        "你是 SectorBreaker V2 Master Agent。读取 State，选择 Tools，观察结果，更新记忆。"
        "不要把 L1-L5 当成死流程。必须输出结构化 JSON action。"
    )
