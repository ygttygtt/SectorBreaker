"""Backend-owned workflow definition for the single Agent Kernel path."""

from backend.app.schemas import WorkflowDefinition, WorkflowEdge, WorkflowNode


def build_agent_kernel_workflow_definition() -> WorkflowDefinition:
    nodes = [
        WorkflowNode(
            id="initialize_state",
            label="初始化 State",
            node_type="gate",
            group="scope",
            reason="建立知识目标、动态 schema、运行记忆、预算和安全边界。",
        ),
        WorkflowNode(
            id="external_materials",
            label="材料与 Vault 入 State",
            node_type="agent",
            agent_id="report_internalizer",
            group="source",
            reason="把上传材料、导入知识库、引用和低可信线索写入 Agent State。",
        ),
        WorkflowNode(
            id="agent_decide",
            label="Master Agent 决策",
            node_type="gate",
            agent_id="master_agent",
            group="plan",
            reason="读取 State 与工具，决定检索、研究、委派、写作、审查、询问或结束。",
        ),
        WorkflowNode(
            id="tool_execution",
            label="工具执行",
            node_type="agent",
            agent_id="tool_executor",
            group="source",
            reason="执行检索、搜索、材料读取、状态治理和知识写作工具。",
        ),
        WorkflowNode(
            id="state_update",
            label="State 更新",
            node_type="store",
            group="evidence",
            reason="把 Observation 内化为证据、主张、实体、问题、ArtifactMemory 和决策记录。",
        ),
        WorkflowNode(
            id="artifact_writing",
            label="知识库修订",
            node_type="agent",
            agent_id="knowledge_editor",
            group="synthesis",
            reason="创建或修订 Obsidian Markdown，并保留证据与版本关系。",
        ),
        WorkflowNode(
            id="artifact_review",
            label="知识质量审查",
            node_type="gate",
            agent_id="artifact_reviewer",
            group="qa",
            reason="检查内容、证据、链接和维护目标是否满足。",
        ),
        WorkflowNode(
            id="human_feedback",
            label="人在回路",
            node_type="human",
            group="qa",
            reason="权限、冲突、证据或边界不清时请求用户决策。",
        ),
        WorkflowNode(
            id="export",
            label="Obsidian 导出",
            node_type="agent",
            agent_id="export_writer",
            group="export",
            reason="导出当前活跃知识版本与可审计状态包。",
        ),
    ]
    edges = [
        WorkflowEdge(id="e-init-materials", source="initialize_state", target="external_materials", label="读取材料"),
        WorkflowEdge(id="e-materials-decide", source="external_materials", target="agent_decide", label="State 输入"),
        WorkflowEdge(id="e-decide-tool", source="agent_decide", target="tool_execution", label="选择行动"),
        WorkflowEdge(id="e-tool-state", source="tool_execution", target="state_update", label="Observation"),
        WorkflowEdge(id="e-state-loop", source="state_update", target="agent_decide", label="继续判断"),
        WorkflowEdge(id="e-tool-write", source="tool_execution", target="artifact_writing", label="知识变更"),
        WorkflowEdge(id="e-write-review", source="artifact_writing", target="artifact_review", label="审查"),
        WorkflowEdge(id="e-review-loop", source="artifact_review", target="agent_decide", label="补证或修订"),
        WorkflowEdge(id="e-decide-human", source="agent_decide", target="human_feedback", label="需要反馈"),
        WorkflowEdge(id="e-human-loop", source="human_feedback", target="agent_decide", label="反馈入 State"),
        WorkflowEdge(id="e-decide-export", source="agent_decide", target="export", label="完成"),
    ]
    return WorkflowDefinition(nodes=nodes, edges=edges)
