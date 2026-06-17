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
  Target,
  Database,
  FileText,
  Map,
  Search,
  Download,
  CheckCircle2,
  Loader2,
  Circle,
  AlertCircle,
  GitBranch,
} from "lucide-react";

// ── Gate definitions ─────────────────────────────────────────

export interface GateDef {
  id: string;
  label: string;
  agent: string;
  desc: string;
  pause: boolean;
  icon: typeof Target;
}

export const GATE_DEFS: GateDef[] = [
  { id: "scope", label: "范围确认", agent: "Research Planner", desc: "分析领域边界、关键问题、数据口径", pause: true, icon: Target },
  { id: "evidence", label: "证据收集", agent: "Search Scout", desc: "搜索行业概况、玩家、机会", pause: false, icon: Database },
  { id: "research_frame", label: "研究框架", agent: "Research Planner", desc: "生成研究板块、关键问题、学习路径", pause: true, icon: FileText },
  { id: "knowledge_map", label: "知识地图", agent: "Knowledge Mapper", desc: "并行生成 11 个产物", pause: false, icon: Map },
  { id: "opportunity", label: "机会地图", agent: "Opportunity Analyst", desc: "识别机会假设、验证路径", pause: true, icon: Search },
  { id: "qa_critic", label: "质量门", agent: "QA Critic", desc: "检查产物完整性、证据引用", pause: false, icon: GitBranch },
  { id: "export", label: "导出", agent: "Export Writer", desc: "生成 Obsidian Markdown 知识库", pause: false, icon: Download },
];

export type GateStatus = "done" | "current" | "next" | "error" | "waiting";

// ── Status colors ────────────────────────────────────────────

const STATUS_COLORS: Record<GateStatus, { color: string; bg: string }> = {
  done: { color: "#106b5d", bg: "#e9f3ef" },
  current: { color: "#d4a017", bg: "#fff8e1" },
  next: { color: "#c7d2df", bg: "#f6f7f9" },
  error: { color: "#dc3545", bg: "#fff5f5" },
  waiting: { color: "#d4a017", bg: "#fff8e1" },
};

// ── Dagre layout helper ──────────────────────────────────────

function getLayoutedElements(nodes: Node[], edges: Edge[], isCompact: boolean) {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const nodeW = isCompact ? 140 : 220;
  const nodeH = isCompact ? 50 : 80;
  const rankSep = isCompact ? 60 : 100;
  const nodeSep = isCompact ? 30 : 50;

  dagreGraph.setGraph({
    rankdir: "LR",       // left-to-right flow
    ranksep: rankSep,    // space between ranks
    nodesep: nodeSep,    // space between nodes in same rank
    marginx: 20,
    marginy: 20,
  });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeW, height: nodeH });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - nodeW / 2,
        y: nodeWithPosition.y - nodeH / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

// ── Gate Node ────────────────────────────────────────────────

function GateNodeComponent({ data }: NodeProps) {
  const { label, agent, desc, status, pause, isCompact } = data as {
    label: string;
    agent: string;
    desc: string;
    status: GateStatus;
    pause: boolean;
    isCompact: boolean;
  };

  const cfg = STATUS_COLORS[status] || STATUS_COLORS.next;
  const Icon = status === "done" ? CheckCircle2
    : status === "current" ? Loader2
    : status === "waiting" ? Loader2
    : Circle;

  return (
    <div
      style={{
        background: "#fff",
        border: `2px solid ${cfg.color}`,
        borderRadius: 10,
        padding: isCompact ? "8px 12px" : "12px 16px",
        width: isCompact ? 140 : 220,
        boxShadow: status === "current" || status === "waiting"
          ? `0 0 16px ${cfg.color}30`
          : "0 1px 4px rgba(0,0,0,0.06)",
        transition: "all 0.3s ease",
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: cfg.color, width: 8, height: 8, border: "2px solid #fff" }}
      />

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div
          style={{
            width: 26,
            height: 26,
            borderRadius: 6,
            background: cfg.bg,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Icon
            size={14}
            style={{
              color: cfg.color,
              animation: (status === "current" || status === "waiting") ? "spin 1s linear infinite" : "none",
            }}
          />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: isCompact ? 12 : 14, color: "#16191f", lineHeight: 1.2 }}>
            {label}
          </div>
          {!isCompact && (
            <div style={{ fontSize: 10, color: "#8a94a3", marginTop: 1 }}>{agent}</div>
          )}
        </div>
        {pause && (
          <span
            style={{
              fontSize: 9,
              background: "#fff8e1",
              color: "#d4a017",
              padding: "1px 5px",
              borderRadius: 3,
              fontWeight: 700,
              flexShrink: 0,
            }}
          >
            审阅
          </span>
        )}
      </div>

      {/* Description */}
      {!isCompact && (
        <div style={{ fontSize: 11, color: "#6d716f", lineHeight: 1.4, marginTop: 6 }}>
          {desc}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Right}
        style={{ background: cfg.color, width: 8, height: 8, border: "2px solid #fff" }}
      />
    </div>
  );
}

// ── QA Node ──────────────────────────────────────────────────

function QANodeComponent({ data }: NodeProps) {
  const { status, isCompact } = data as { status: GateStatus; isCompact: boolean };
  const cfg = STATUS_COLORS[status] || STATUS_COLORS.next;
  const Icon = status === "error" ? AlertCircle
    : status === "done" ? CheckCircle2
    : GitBranch;

  return (
    <div
      style={{
        background: status === "error" ? "#fff5f5" : "#fff",
        border: `2px dashed ${cfg.color}`,
        borderRadius: 10,
        padding: isCompact ? "8px 12px" : "12px 16px",
        width: isCompact ? 140 : 220,
        textAlign: "center",
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: cfg.color, width: 8, height: 8, border: "2px solid #fff" }}
      />

      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
        <Icon size={isCompact ? 14 : 16} style={{ color: cfg.color }} />
        <span style={{ fontWeight: 700, fontSize: isCompact ? 12 : 14, color: "#34373d" }}>
          质量门
        </span>
      </div>

      {!isCompact && (
        <div style={{ fontSize: 10, color: "#8a94a3", marginTop: 3 }}>
          检查产物完整性
        </div>
      )}

      {/* Pass output (right) */}
      <Handle
        type="source"
        position={Position.Right}
        id="pass"
        style={{ background: "#106b5d", width: 8, height: 8, border: "2px solid #fff", top: "35%" }}
      />
      {/* Fail output (bottom) */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="fail"
        style={{ background: "#dc3545", width: 8, height: 8, border: "2px solid #fff" }}
      />
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────

interface WorkflowEditorProps {
  currentGate?: string;
  gateStatuses?: Record<string, GateStatus>;
  isCompact?: boolean;
  showMinimap?: boolean;
  showControls?: boolean;
}

export function WorkflowEditor({
  currentGate = "scope",
  gateStatuses,
  isCompact = false,
  showMinimap = false,
  showControls = true,
}: WorkflowEditorProps) {
  const getStatus = (gateId: string): GateStatus => {
    if (gateStatuses?.[gateId]) return gateStatuses[gateId];
    const currentIdx = GATE_DEFS.findIndex((g) => g.id === currentGate);
    const gateIdx = GATE_DEFS.findIndex((g) => g.id === gateId);
    if (currentIdx === -1) return "next";
    if (gateIdx < currentIdx) return "done";
    if (gateIdx === currentIdx) return "current";
    return "next";
  };

  const { nodes, edges } = useMemo(() => {
    // Build raw nodes
    const rawNodes: Node[] = GATE_DEFS.map((gate) => ({
      id: gate.id,
      type: gate.id === "qa_critic" ? "qaNode" : "gateNode",
      position: { x: 0, y: 0 }, // dagre will compute
      data: {
        label: gate.label,
        agent: gate.agent,
        desc: gate.desc,
        status: getStatus(gate.id),
        pause: gate.pause,
        isCompact,
      },
    }));

    // Build raw edges
    const rawEdges: Edge[] = [
      { id: "e1", source: "scope", target: "evidence" },
      { id: "e2", source: "evidence", target: "research_frame" },
      { id: "e3", source: "research_frame", target: "knowledge_map" },
      { id: "e4", source: "knowledge_map", target: "opportunity" },
      { id: "e5", source: "opportunity", target: "qa_critic" },
      { id: "e6", source: "qa_critic", sourceHandle: "pass", target: "export" },
      { id: "e7", source: "qa_critic", sourceHandle: "fail", target: "opportunity" },
    ];

    // Apply dagre layout
    return getLayoutedElements(rawNodes, rawEdges, isCompact);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentGate, gateStatuses, isCompact]);

  // Style edges based on status
  const styledEdges: Edge[] = useMemo(
    () =>
      edges.map((edge) => {
        const sourceStatus = getStatus(edge.source);
        const isActive = sourceStatus === "done" || sourceStatus === "current";
        const isFail = edge.id === "e7";

        return {
          ...edge,
          type: "smoothstep",
          style: {
            strokeWidth: 2,
            stroke: isFail
              ? (sourceStatus === "error" ? "#dc3545" : "#dfe5ec")
              : isActive
              ? "#106b5d"
              : "#dfe5ec",
            strokeDasharray: isFail ? "6,4" : undefined,
          },
          animated: sourceStatus === "current" && !isFail,
          markerEnd: isFail
            ? { type: MarkerType.ArrowClosed, color: "#dc3545", width: 14, height: 14 }
            : undefined,
          label: isFail ? "回退" : undefined,
          labelStyle: { fontSize: 10, fontWeight: 600, color: "#dc3545" },
        };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [edges, currentGate, gateStatuses]
  );

  const nodeTypes: NodeTypes = useMemo(
    () => ({ gateNode: GateNodeComponent, qaNode: QANodeComponent }),
    []
  );

  const height = isCompact ? 260 : 440;

  return (
    <div style={{ width: "100%", height }}>
      <ReactFlow
        nodes={nodes}
        edges={styledEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable={true}
        nodesConnectable={false}
        elementsSelectable={false}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#edf0f4" gap={isCompact ? 12 : 20} />
        {showControls && <Controls showInteractive={false} />}
        {showMinimap && (
          <MiniMap
            nodeColor={(node) => {
              const status = (node.data as { status?: GateStatus })?.status || "next";
              return STATUS_COLORS[status]?.color || "#ccc";
            }}
            style={{ background: "#f6f7f9" }}
          />
        )}
      </ReactFlow>
    </div>
  );
}
