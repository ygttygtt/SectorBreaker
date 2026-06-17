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
  done: { color: "var(--green)", bg: "var(--green-light)" },
  current: { color: "var(--gold)", bg: "var(--gold-light)" },
  next: { color: "var(--gray-400)", bg: "var(--gray-100)" },
  error: { color: "var(--red)", bg: "#fff5f5" },
  waiting: { color: "var(--gold)", bg: "var(--gold-light)" },
};

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
        borderRadius: 12,
        padding: isCompact ? "10px 14px" : "16px 20px",
        minWidth: isCompact ? 120 : 200,
        maxWidth: isCompact ? 150 : 260,
        boxShadow: status === "current" || status === "waiting"
          ? `0 0 24px ${cfg.color}40`
          : "0 2px 8px rgba(0,0,0,0.06)",
        transition: "all 0.3s ease",
        cursor: "default",
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: cfg.color, width: 10, height: 10, border: "2px solid #fff" }}
      />

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: isCompact ? 0 : 10 }}>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            background: cfg.bg,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Icon
            size={16}
            style={{
              color: cfg.color,
              animation: (status === "current" || status === "waiting") ? "spin 1s linear infinite" : "none",
            }}
          />
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: isCompact ? 13 : 15, color: "var(--gray-900)", lineHeight: 1.2 }}>
            {label}
          </div>
          {!isCompact && (
            <div style={{ fontSize: 11, color: "var(--gray-500)", marginTop: 1 }}>{agent}</div>
          )}
        </div>
        {pause && (
          <span
            style={{
              fontSize: 9,
              background: "var(--gold-light)",
              color: "var(--gold)",
              padding: "2px 6px",
              borderRadius: 4,
              fontWeight: 700,
              marginLeft: "auto",
              whiteSpace: "nowrap",
            }}
          >
            人工审阅
          </span>
        )}
      </div>

      {/* Description */}
      {!isCompact && (
        <div style={{ fontSize: 12, color: "var(--gray-600)", lineHeight: 1.5, marginTop: 6 }}>
          {desc}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Right}
        style={{ background: cfg.color, width: 10, height: 10, border: "2px solid #fff" }}
      />
    </div>
  );
}

// ── QA Node (special) ────────────────────────────────────────

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
        borderRadius: 12,
        padding: isCompact ? "10px 14px" : "14px 18px",
        minWidth: isCompact ? 100 : 160,
        textAlign: "center",
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: cfg.color, width: 10, height: 10, border: "2px solid #fff" }}
      />

      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
        <Icon size={isCompact ? 14 : 18} style={{ color: cfg.color }} />
        <span style={{ fontWeight: 700, fontSize: isCompact ? 12 : 14, color: "var(--gray-800)" }}>
          质量门
        </span>
      </div>

      {!isCompact && (
        <div style={{ fontSize: 11, color: "var(--gray-500)", marginTop: 4 }}>
          检查产物完整性、证据引用
        </div>
      )}

      {/* Pass output (right) */}
      <Handle
        type="source"
        position={Position.Right}
        id="pass"
        style={{ background: "var(--green)", width: 10, height: 10, border: "2px solid #fff", top: "35%" }}
      />
      {/* Fail output (bottom) */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="fail"
        style={{ background: "var(--red)", width: 10, height: 10, border: "2px solid #fff" }}
      />
    </div>
  );
}

// ── Layout positions ─────────────────────────────────────────

function getPositions(isCompact: boolean) {
  const w = isCompact ? 180 : 280;
  const h = isCompact ? 100 : 140;
  const gap = isCompact ? 40 : 60;

  // Snake layout: left-to-right, then right-to-left
  return [
    { x: 0, y: 0 },                                    // scope
    { x: w + gap, y: 0 },                              // evidence
    { x: (w + gap) * 2, y: 0 },                        // research_frame
    { x: (w + gap) * 2, y: h + gap },                  // knowledge_map
    { x: w + gap, y: h + gap },                        // opportunity
    { x: 0, y: h + gap },                              // qa_critic
    { x: 0, y: (h + gap) * 2 },                        // export
  ];
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

  const positions = getPositions(isCompact);

  const nodes: Node[] = useMemo(
    () =>
      GATE_DEFS.map((gate, i) => ({
        id: gate.id,
        type: gate.id === "qa_critic" ? "qaNode" : "gateNode",
        position: positions[i],
        data: {
          label: gate.label,
          agent: gate.agent,
          desc: gate.desc,
          status: getStatus(gate.id),
          pause: gate.pause,
          isCompact,
        },
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [currentGate, gateStatuses, isCompact]
  );

  const edges: Edge[] = useMemo(() => {
    const baseStyle = { strokeWidth: 2.5 };

    const defs: Edge[] = [
      { id: "e1", source: "scope", target: "evidence" },
      { id: "e2", source: "evidence", target: "research_frame" },
      { id: "e3", source: "research_frame", target: "knowledge_map" },
      { id: "e4", source: "knowledge_map", target: "opportunity" },
      { id: "e5", source: "opportunity", target: "qa_critic" },
      {
        id: "e6",
        source: "qa_critic",
        sourceHandle: "pass",
        target: "export",
        label: "通过",
      },
      {
        id: "e7",
        source: "qa_critic",
        sourceHandle: "fail",
        target: "opportunity",
        label: "回退",
      },
    ];

    return defs.map((edge) => {
      const sourceStatus = getStatus(edge.source);
      const isActive = sourceStatus === "done" || sourceStatus === "current";
      const isFail = edge.id === "e7";

      return {
        ...edge,
        style: {
          ...baseStyle,
          stroke: isFail
            ? (sourceStatus === "error" ? "var(--red)" : "var(--gray-300)")
            : isActive
            ? "var(--green)"
            : "var(--gray-300)",
          strokeDasharray: isFail ? "6,4" : undefined,
        },
        animated: sourceStatus === "current" && !isFail,
        markerEnd: isFail
          ? { type: MarkerType.ArrowClosed, color: "var(--red)", width: 16, height: 16 }
          : undefined,
        labelStyle: {
          fontSize: 11,
          fontWeight: 600,
          color: isFail ? "var(--red)" : "var(--green)",
        },
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentGate, gateStatuses]);

  const nodeTypes: NodeTypes = useMemo(
    () => ({ gateNode: GateNodeComponent, qaNode: QANodeComponent }),
    []
  );

  const height = isCompact ? 280 : 480;

  return (
    <div style={{ width: "100%", height }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        nodesDraggable={true}
        nodesConnectable={false}
        elementsSelectable={false}
        minZoom={0.4}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="var(--gray-200)" gap={isCompact ? 16 : 24} />
        {showControls && <Controls showInteractive={false} />}
        {showMinimap && (
          <MiniMap
            nodeColor={(node) => {
              const status = (node.data as { status?: GateStatus })?.status || "next";
              return STATUS_COLORS[status]?.color || "#ccc";
            }}
            style={{ background: "var(--gray-100)" }}
          />
        )}
      </ReactFlow>
    </div>
  );
}
