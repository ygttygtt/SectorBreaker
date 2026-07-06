"""Human-in-the-loop tool for the V2 Agent Kernel."""

from __future__ import annotations

from backend.app.agent_kernel.models import KernelObservation, ToolSpec
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry, schema


def register_human_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="ask_user",
            description="Pause and ask the user when information is missing, boundary is unclear, or unsafe research needs confirmation.",
            args_schema=schema({"question": {"type": "string"}, "reason": {"type": "string"}}, required=["question", "reason"]),
        ),
        ask_user,
    )


async def ask_user(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    question = str(tool_call.args.get("question") or "").strip()
    reason = str(tool_call.args.get("reason") or tool_call.reason or "").strip()
    return KernelObservation(
        tool_name="ask_user",
        success=True,
        summary=f"需要用户反馈：{question}",
        data={"question": question, "reason": reason, "state_version": context.state.state_version},
        requires_human=True,
    )
