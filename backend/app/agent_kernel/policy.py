"""LLM policy for the V2 Agent Kernel."""

from __future__ import annotations

import json
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
            repaired = await self._repair_decision_json(prompt=prompt, error=exc)
            if repaired is not None:
                return repaired
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

    async def _repair_decision_json(self, *, prompt: str, error: Exception) -> AgentDecision | None:
        if self.llm_provider is None:
            return None
        repair_prompt = (
            "上一次 AgentDecision 输出不是合法 JSON，导致解析失败。\n"
            f"错误类型：{type(error).__name__}\n"
            f"错误摘要：{str(error)[:1000]}\n\n"
            "请重新输出一个合法 JSON 对象，必须符合以下字段：\n"
            "- thought_summary: string\n"
            "- action_type: call_tool | update_state | write_artifact | review_artifact | ask_user | finish | block\n"
            "- current_goal: string，说明当前阶段目标\n"
            "- plan_steps: string[]，给出短计划\n"
            "- progress_check: string，说明当前 State 离目标还差什么\n"
            "- tool_call: 当 action_type 需要单个工具时包含 {tool_name, args, reason}\n"
            "- tool_calls: 当需要连续工具时可包含多个 {tool_name, args, reason}，例如先 evaluate_coverage 再 search_web\n"
            "- expected_observation: string\n"
            "- stop_reason: finish 或 block 时必须填写\n\n"
            "不要输出 Markdown，不要解释，不要代码块，只输出 JSON。\n\n"
            "原始任务上下文如下：\n"
            f"{prompt[-12000:]}"
        )
        try:
            content = await self.llm_provider.complete([ChatMessage(role="user", content=repair_prompt)])
            return AgentDecision.model_validate(_loads_json_object(content))
        except Exception:
            return None

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
            "必须填写 current_goal、plan_steps、progress_check，让用户能看到 Agent 的阶段性判断。"
            "可以使用 tool_calls 输出多个顺序工具调用；运行时会按顺序执行并逐个更新 State。"
            "不确定某层是否可写时，优先调用 evaluate_coverage；连续低价值搜索后，优先调用 reflect_on_progress。"
            "如果要写文档，action_type 使用 write_artifact，tool_call 或 tool_calls 中的 tool_name 使用 write_layer_document。"
            "如果要审查文档，action_type 使用 review_artifact，tool_call 或 tool_calls 中的 tool_name 使用 review_artifact。"
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


def _loads_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("AgentDecision repair output must be a JSON object")
    return value
