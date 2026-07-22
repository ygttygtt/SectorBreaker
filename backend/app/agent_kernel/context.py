"""Context construction for Agent Kernel LLM decisions."""

from __future__ import annotations

import json

from backend.app.agent_kernel.models import KernelTraceEvent, ToolSpec
from backend.app.agent_state import ContextPackBuilder, SectorBreakerState
from backend.app.schemas import Artifact


class KernelContextBuilder:
    """Build a compact, explicit context instead of dumping all storage."""

    def __init__(self) -> None:
        self._context_pack_builder = ContextPackBuilder()

    def build_prompt_context(
        self,
        *,
        state: SectorBreakerState,
        tools: list[ToolSpec],
        trace_tail: list[KernelTraceEvent],
        artifacts: list[Artifact] | None = None,
    ) -> str:
        pack = self._context_pack_builder.build(
            state,
            layer_id=state.current_layer_id,
            task_memory=state.working_memory.get(state.current_task_id or ""),
            active_task=state.meta_context.user_goal,
        )
        layers = [
            {
                "id": _layer_value(layer.id),
                "title": layer.title,
                "goal": layer.goal,
                "priority_weight": layer.priority_weight,
                "prerequisite_layer_ids": [_layer_value(item) for item in layer.prerequisite_layer_ids],
                "guiding_questions": layer.guiding_questions,
                "completion_criteria": layer.completion_criteria,
                "coverage_status": layer.coverage_status.value,
                "coverage_score": layer.coverage_score,
                "ready_to_write": layer.ready_to_write,
                "coverage_notes": layer.coverage_notes,
            }
            for layer in state.knowledge_schema.layers
        ]
        trace = [
            {
                "kind": event.kind.value,
                "message": event.message,
                "data": event.data,
            }
            for event in trace_tail[-10:]
        ]
        tool_specs = [tool.model_dump(mode="json") for tool in tools]
        artifact_summaries = [
            {
                "id": artifact.id,
                "title": artifact.title,
                "content_path": artifact.content_path,
                "schema_version": artifact.schema_version,
                "chars": len(artifact.content),
                "source_evidence_ids": artifact.source_evidence_ids[:12],
            }
            for artifact in (artifacts or [])
        ]
        return (
            "## Meta Context\n"
            f"{json.dumps(state.meta_context.model_dump(mode='json'), ensure_ascii=False, indent=2)}\n\n"
            "## Knowledge Schema / Coverage\n"
            f"{json.dumps(layers, ensure_ascii=False, indent=2)}\n\n"
            "## Curated ContextPack\n"
            f"{pack.to_prompt_text()}\n\n"
            "## Artifact Memory\n"
            f"{json.dumps({'artifact_count': len(artifact_summaries), 'artifacts': artifact_summaries}, ensure_ascii=False, indent=2)}\n\n"
            "## Knowledge Management Control Plane\n"
            f"{json.dumps({
                'vault_import_id': state.vault_import_id,
                'latest_health_report_id': state.latest_health_report_id,
                'maintenance_task_ids': state.maintenance_task_ids,
                'maintenance_task_summaries': state.maintenance_task_summaries,
                'active_maintenance_objective': state.active_maintenance_objective,
                'delegation_log': state.delegation_log[-12:],
                'human_feedback': state.human_feedback[-12:],
                'autonomy_policy': state.autonomy_policy.model_dump(mode='json'),
            }, ensure_ascii=False, indent=2)}\n\n"
            "## Available Tools\n"
            f"{json.dumps(tool_specs, ensure_ascii=False, indent=2)}\n\n"
            "## Recent Agent Trace\n"
            f"{json.dumps(trace, ensure_ascii=False, indent=2)}"
        )


def _layer_value(layer_id) -> str:
    return layer_id.value if hasattr(layer_id, "value") else str(layer_id)
