import { useEffect, useMemo, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  type NodeProps,
  Handle,
  Position,
  MarkerType,
  useReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import dagre from "dagre";
import "@xyflow/react/dist/style.css";
import {
  AlertCircle,
  CheckCircle2,
  Circle,
  Clock3,
  Database,
  FileText,
  GitBranch,
  Loader2,
  PackageCheck,
  Search,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import type { WorkflowDefinition, WorkflowNode } from "../api/client";

export type NodeStatus =
  | "pending"
  | "enabled"
  | "skipped"
  | "running"
  | "waiting_for_user"
  | "degraded"
  | "blocked"
  | "failed"
  | "completed";

const STATUS_STYLE: Record<NodeStatus, { color: string; bg: string; label: string }> = {
  pending: { color: "#a7b0bd", bg: "#f6f7f9", label: "待运行" },
  enabled: { color: "#2d5d9f", bg: "#eef3ff", label: "已启用" },
  skipped: { color: "#8a94a3", bg: "#f2f4f7", label: "已跳过" },
  running: { color: "#d4a017", bg: "#fff8e1", label: "运行中" },
  waiting_for_user: { color: "#9a6b00", bg: "#fff8e1", label: "等待确认" },
  degraded: { color: "#b7791f", bg: "#fff8e1", label: "降级" },
  blocked: { color: "#dc3545", bg: "#fff5f5", label: "阻塞" },
  failed: { color: "#dc3545", bg: "#fff5f5", label: "失败" },
  completed: { color: "#106b5d", bg: "#e9f3ef", label: "完成" },
};

const PERSONAL_DEFINITION: WorkflowDefinition = {
  schema_version: "1",
  nodes: [
    { id: "initialize_state", label: "初始化 State", node_type: "gate", group: "scope", status: "pending", reason: "建立目标、L1-L5 认知 schema、运行记忆、工具预算和安全边界。", details: {} },
    { id: "external_materials", label: "外部材料入 State", node_type: "agent", group: "source", status: "pending", reason: "把上传报告、用户材料、引用和低可信线索写入 Agent State。", details: {} },
    { id: "agent_decide", label: "LLM 大脑决策", node_type: "gate", group: "plan", status: "pending", reason: "LLM 读取 State 与 Tools，决定下一步搜索、读材料、写作、审查、问用户或结束。", details: {} },
    { id: "tool_execution", label: "工具执行", node_type: "agent", group: "source", status: "pending", reason: "执行 search_web、read_uploaded_report、retrieve_project_memory、write_layer_document 等真实工具。", details: {} },
    { id: "state_update", label: "State 更新", node_type: "store", group: "evidence", status: "pending", reason: "把 Observation 内化为 source memory、claims、entities、open questions、artifact refs 和 decision log。", details: {} },
    { id: "artifact_writing", label: "知识库写作", node_type: "agent", group: "synthesis", status: "pending", reason: "当 Agent 判断材料足够时，通过工具写入 V2 L1-L5 / 动态 schema Obsidian 文档。", details: {} },
    { id: "artifact_review", label: "详实度审查", node_type: "gate", group: "qa", status: "pending", reason: "检查是否详实、证据关联、Obsidian 友好；不足时回到 Agent 决策继续补搜或修订。", details: {} },
    { id: "human_feedback", label: "人在回路", node_type: "human", group: "qa", status: "pending", reason: "边界、材料或风险不清时，Agent 可以暂停并请求用户反馈。", details: {} },
    { id: "export", label: "Obsidian 导出 / RAG", node_type: "agent", group: "export", status: "pending", reason: "持久化 Agent 写出的 Markdown 产物，并支持后续项目问答。", details: {} },
  ],
  edges: [
    { id: "e1", source: "initialize_state", target: "external_materials", label: "读取材料" },
    { id: "e2", source: "external_materials", target: "agent_decide", label: "State 输入" },
    { id: "e3", source: "agent_decide", target: "tool_execution", label: "选择工具" },
    { id: "e4", source: "tool_execution", target: "state_update", label: "Observation" },
    { id: "e5", source: "state_update", target: "agent_decide", label: "继续判断" },
    { id: "e6", source: "tool_execution", target: "artifact_writing", label: "写作工具" },
    { id: "e7", source: "artifact_writing", target: "artifact_review", label: "审查" },
    { id: "e8", source: "artifact_review", target: "agent_decide", label: "补搜 / 修订" },
    { id: "e9", source: "agent_decide", target: "human_feedback", label: "需要反馈" },
    { id: "e10", source: "human_feedback", target: "agent_decide", label: "反馈入 State" },
    { id: "e11", source: "agent_decide", target: "export", label: "完成" },
  ],
};

const TALENT_DEFINITION: WorkflowDefinition = {
  schema_version: "1",
  nodes: [
    { id: "scope", label: "定义岗位方向", node_type: "gate", group: "scope", status: "pending", reason: "明确目标岗位、城市/市场范围和样本策略。", details: {} },
    { id: "talent_source_intake", label: "JD / 报告上传", node_type: "agent", group: "source", status: "pending", reason: "优先读取用户上传的 JD、岗位说明和外部 AI 报告。", details: {} },
    { id: "boss_job_intake", label: "Boss 职位样本", node_type: "agent", group: "source", status: "pending", reason: "可选接入本地 Boss CLI，采集结构化职位样本。", details: {} },
    { id: "source_collection", label: "搜索补充", node_type: "agent", group: "source", status: "pending", reason: "材料不足时补充公开网页和岗位/技能相关资料。", details: {} },
    { id: "source_coverage", label: "信源覆盖矩阵", node_type: "store", group: "evidence", status: "pending", reason: "统计 JD、Boss、外部报告、搜索证据和缺口。", details: {} },
    { id: "jd_signal_extraction", label: "岗位信号抽取", node_type: "agent", group: "analysis", status: "pending", reason: "抽取公司、地点、薪资、经验、职责、技能和工具。", details: {} },
    { id: "skill_normalization", label: "技能矩阵归一", node_type: "group", group: "synthesis", status: "pending", reason: "合并同义技能，生成频次、层级和代表证据。", details: {} },
    { id: "talent_synthesis", label: "人才情报综合", node_type: "agent", group: "synthesis", status: "pending", reason: "生成岗位画像、学习路径、作品集要求和待验证问题。", details: {} },
    { id: "export", label: "企业 Vault / RAG", node_type: "agent", group: "export", status: "pending", reason: "导出人才需求 Obsidian Vault，并支持基于项目资料问答。", details: {} },
  ],
  edges: [
    { id: "e1", source: "scope", target: "talent_source_intake" },
    { id: "e2", source: "scope", target: "boss_job_intake" },
    { id: "e3", source: "scope", target: "source_collection" },
    { id: "e4", source: "talent_source_intake", target: "source_coverage" },
    { id: "e5", source: "boss_job_intake", target: "source_coverage" },
    { id: "e6", source: "source_collection", target: "source_coverage" },
    { id: "e7", source: "source_coverage", target: "jd_signal_extraction" },
    { id: "e8", source: "jd_signal_extraction", target: "skill_normalization" },
    { id: "e9", source: "skill_normalization", target: "talent_synthesis" },
    { id: "e10", source: "talent_synthesis", target: "export" },
  ],
};

const DEFAULT_DEFINITION_BY_VARIANT = {
  domain_knowledge: PERSONAL_DEFINITION,
  talent_demand: TALENT_DEFINITION,
};

const GROUP_ORDER = [
  "scope",
  "plan",
  "source",
  "evidence",
  "analysis",
  "synthesis",
  "qa",
  "export",
];

function iconFor(node: WorkflowNode, status: NodeStatus) {
  if (status === "running") return Loader2;
  if (status === "completed") return CheckCircle2;
  if (status === "blocked" || status === "failed") return AlertCircle;
  if (node.node_type === "human") return UserCheck;
  if (node.group === "source") return Search;
  if (node.group === "evidence") return Database;
  if (node.group === "analysis") return GitBranch;
  if (node.group === "qa") return ShieldCheck;
  if (node.group === "export") return PackageCheck;
  if (node.node_type === "gate") return FileText;
  return Circle;
}

function getLayoutedElements(nodes: Node[], edges: Edge[], isCompact: boolean) {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  const nodeW = isCompact ? 160 : 220;
  const nodeH = isCompact ? 64 : 96;
  dagreGraph.setGraph({
    rankdir: "TB",
    ranksep: isCompact ? 44 : 88,
    nodesep: isCompact ? 22 : 44,
    edgesep: isCompact ? 16 : 28,
    marginx: 28,
    marginy: 28,
  });
  nodes.forEach((node) => dagreGraph.setNode(node.id, { width: nodeW, height: nodeH }));
  edges.forEach((edge) => dagreGraph.setEdge(edge.source, edge.target));
  dagre.layout(dagreGraph);
  return {
    nodes: nodes.map((node) => {
      const pos = dagreGraph.node(node.id);
      return { ...node, position: { x: pos.x - nodeW / 2, y: pos.y - nodeH / 2 } };
    }),
    edges,
  };
}

function FlowNode({ data }: NodeProps) {
  const node = data.node as WorkflowNode;
  const isCompact = Boolean(data.isCompact);
  const status = (data.status as NodeStatus) || "pending";
  const style = STATUS_STYLE[status];
  const Icon = iconFor(node, status);
  const isActive = status === "running" || status === "waiting_for_user";

  return (
    <div
      className={`workflow-node workflow-node--${status}`}
      style={{
        borderColor: style.color,
        boxShadow: isActive ? `0 0 0 4px ${style.bg}, 0 10px 24px rgba(0,0,0,.08)` : undefined,
        width: isCompact ? 150 : 220,
      }}
    >
      <Handle type="target" position={Position.Top} className="workflow-handle" style={{ background: style.color }} />
      <div className="workflow-node-head">
        <span className="workflow-node-icon" style={{ color: style.color, background: style.bg }}>
          <Icon size={isCompact ? 14 : 16} className={status === "running" ? "spinner" : ""} />
        </span>
        <div className="workflow-node-title">
          <strong>{node.label}</strong>
          {!isCompact && <span>{node.agent_id ?? node.node_type}</span>}
        </div>
      </div>
      {!isCompact && (
        <p className="workflow-node-reason">
          {node.reason || (node.status === "skipped" ? "本次计划未启用" : STATUS_STYLE[status].label)}
        </p>
      )}
      <span className="workflow-node-badge" style={{ color: style.color, background: style.bg }}>
        {style.label}
      </span>
      <Handle type="source" position={Position.Bottom} className="workflow-handle" style={{ background: style.color }} />
    </div>
  );
}

interface WorkflowEditorProps {
  definition?: WorkflowDefinition | null;
  activeNodeId?: string;
  nodeStatuses?: Record<string, NodeStatus>;
  variant?: "domain_knowledge" | "talent_demand";
  isCompact?: boolean;
  showMinimap?: boolean;
  showControls?: boolean;
  fillHeight?: boolean;
  onNodeClick?: (node: WorkflowNode) => void;
}

function WorkflowEditorInner({
  definition,
  activeNodeId,
  nodeStatuses,
  variant = "domain_knowledge",
  isCompact = false,
  showMinimap = false,
  showControls = true,
  fillHeight = false,
  onNodeClick,
}: WorkflowEditorProps) {
  const reactFlow = useReactFlow();
  const firstFitRef = useRef(false);
  const flowDefinition = definition ?? DEFAULT_DEFINITION_BY_VARIANT[variant];
  const sortedNodes = useMemo(
    () =>
      [...flowDefinition.nodes].sort((a, b) => {
        const groupDelta = GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group);
        return groupDelta || a.id.localeCompare(b.id);
      }),
    [flowDefinition.nodes]
  );

  const { nodes, edges } = useMemo(() => {
    const rawNodes: Node[] = sortedNodes.map((node) => {
      const status = nodeStatuses?.[node.id] ?? (activeNodeId === node.id ? "running" : (node.status as NodeStatus));
      return {
        id: node.id,
        type: "flowNode",
        position: { x: 0, y: 0 },
        data: { node, status, isCompact },
      };
    });
    const rawEdges: Edge[] = flowDefinition.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label ?? undefined,
      type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, color: "#a7b0bd", width: 14, height: 14 },
      style: { stroke: "#cfd6df", strokeWidth: 1.6 },
    }));
    return getLayoutedElements(rawNodes, rawEdges, isCompact);
  }, [activeNodeId, flowDefinition.edges, isCompact, nodeStatuses, sortedNodes]);

  const nodeTypes: NodeTypes = useMemo(() => ({ flowNode: FlowNode }), []);
  const height = fillHeight ? "100%" : isCompact ? 320 : 640;

  useEffect(() => {
    firstFitRef.current = false;
  }, [definition, variant]);

  useEffect(() => {
    if (!nodes.length) return;
    if (!firstFitRef.current) {
      window.requestAnimationFrame(() => {
        reactFlow.fitView({ padding: isCompact ? 0.16 : 0.24, duration: 350 });
      });
      firstFitRef.current = true;
      return;
    }
    if (!activeNodeId) return;
    const activeNode = nodes.find((node) => node.id === activeNodeId);
    if (!activeNode) return;
    const x = activeNode.position.x + (typeof activeNode.width === "number" ? activeNode.width / 2 : (isCompact ? 80 : 110));
    const y = activeNode.position.y + (typeof activeNode.height === "number" ? activeNode.height / 2 : (isCompact ? 32 : 48));
    window.requestAnimationFrame(() => {
      reactFlow.setCenter(x, y, { zoom: isCompact ? 0.72 : 0.88, duration: 400 });
    });
  }, [activeNodeId, isCompact, nodes, reactFlow]);

  return (
    <div className="workflow-editor" style={{ height }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={Boolean(onNodeClick)}
        minZoom={0.25}
        maxZoom={1.8}
        onNodeClick={(_, node) => {
          const original = (node.data as { node?: WorkflowNode }).node;
          if (original) onNodeClick?.(original);
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#edf0f4" gap={isCompact ? 12 : 18} />
        {showControls && <Controls showInteractive={false} />}
        {showMinimap && (
          <MiniMap
            nodeColor={(node) => {
              const status = ((node.data as { status?: NodeStatus })?.status ?? "pending") as NodeStatus;
              return STATUS_STYLE[status].color;
            }}
            style={{ background: "#f6f7f9" }}
          />
        )}
      </ReactFlow>
    </div>
  );
}

export function WorkflowEditor(props: WorkflowEditorProps) {
  return (
    <ReactFlowProvider>
      <WorkflowEditorInner {...props} />
    </ReactFlowProvider>
  );
}
