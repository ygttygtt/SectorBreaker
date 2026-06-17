import { useMemo } from "react";
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

const DEFAULT_DEFINITION: WorkflowDefinition = {
  schema_version: "1",
  nodes: [
    { id: "scope", label: "范围确认", node_type: "gate", group: "scope", status: "pending", details: {} },
    { id: "supervisor_plan", label: "主管计划", node_type: "gate", group: "plan", status: "pending", details: {} },
    { id: "human_confirm_plan", label: "人工确认计划", node_type: "human", group: "plan", status: "pending", details: {} },
    { id: "source_strategy", label: "信源策略", node_type: "gate", group: "source", status: "pending", details: {} },
    { id: "source_intake", label: "信源接入", node_type: "group", group: "source", status: "pending", details: {} },
    { id: "evidence_ledger", label: "证据账本", node_type: "store", group: "evidence", status: "pending", details: {} },
    { id: "business_database", label: "商业数据库", node_type: "group", group: "analysis", status: "pending", details: {} },
    { id: "qa_critic", label: "质量门", node_type: "gate", group: "qa", status: "pending", details: {} },
    { id: "export", label: "导出", node_type: "agent", group: "export", status: "pending", details: {} },
  ],
  edges: [
    { id: "e1", source: "scope", target: "supervisor_plan" },
    { id: "e2", source: "supervisor_plan", target: "human_confirm_plan" },
    { id: "e3", source: "human_confirm_plan", target: "source_strategy" },
    { id: "e4", source: "source_strategy", target: "source_intake" },
    { id: "e5", source: "source_intake", target: "evidence_ledger" },
    { id: "e6", source: "evidence_ledger", target: "business_database" },
    { id: "e7", source: "business_database", target: "qa_critic" },
    { id: "e8", source: "qa_critic", target: "export" },
  ],
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
  const nodeW = isCompact ? 150 : 220;
  const nodeH = isCompact ? 58 : 92;
  dagreGraph.setGraph({
    rankdir: "LR",
    ranksep: isCompact ? 60 : 94,
    nodesep: isCompact ? 28 : 46,
    marginx: 20,
    marginy: 20,
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
      <Handle type="target" position={Position.Left} className="workflow-handle" style={{ background: style.color }} />
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
      <Handle type="source" position={Position.Right} className="workflow-handle" style={{ background: style.color }} />
    </div>
  );
}

interface WorkflowEditorProps {
  definition?: WorkflowDefinition | null;
  activeNodeId?: string;
  nodeStatuses?: Record<string, NodeStatus>;
  isCompact?: boolean;
  showMinimap?: boolean;
  showControls?: boolean;
  onNodeClick?: (node: WorkflowNode) => void;
}

export function WorkflowEditor({
  definition,
  activeNodeId,
  nodeStatuses,
  isCompact = false,
  showMinimap = false,
  showControls = true,
  onNodeClick,
}: WorkflowEditorProps) {
  const flowDefinition = definition ?? DEFAULT_DEFINITION;
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
  const height = isCompact ? 300 : 520;

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
