import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeTypes,
  type NodeProps,
  Handle,
  Position,
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

const GATES = [
  { id: "scope", label: "范围确认", agent: "Research Planner", desc: "分析领域边界、关键问题、数据口径", pause: true },
  { id: "evidence", label: "证据收集", agent: "Search Scout", desc: "搜索行业概况、玩家、机会", pause: false },
  { id: "research_frame", label: "研究框架", agent: "Research Planner", desc: "生成研究板块、关键问题、学习路径", pause: true },
  { id: "knowledge_map", label: "知识地图", agent: "Knowledge Mapper", desc: "并行生成 11 个产物（行业/市场/玩家/内容/竞品/收入/信任…）", pause: false },
  { id: "opportunity", label: "机会地图", agent: "Opportunity Analyst", desc: "识别机会假设、验证路径", pause: true },
  { id: "qa_critic", label: "质量门", agent: "QA Critic", desc: "检查产物完整性、证据引用", pause: false },
  { id: "export", label: "导出", agent: "Export Writer", desc: "生成 Obsidian Markdown 知识库", pause: false },
] as const;

type GateStatus = "done" | "current" | "next" | "error" | "waiting";

// ── Custom node component ────────────────────────────────────

function GateNode({ data }: NodeProps) {
  const { label, agent, desc, status, pause, isCompact } = data as {
    label: string;
    agent: string;
    desc: string;
    status: GateStatus;
    pause: boolean;
    isCompact: boolean;
  };

  const statusConfig = {
    done: { icon: CheckCircle2, color: "var(--green)", bg: "var(--green-light)" },
    current: { icon: Loader2, color: "var(--gold)", bg: "var(--gold-light)" },
    next: { icon: Circle, color: "var(--gray-400)", bg: "var(--gray-100)" },
    error: { icon: AlertCircle, color: "var(--red)", bg: "#fff5f5" },
    waiting: { icon: Loader2, color: "var(--gold)", bg: "var(--gold-light)" },
  };

  const cfg = statusConfig[status] || statusConfig.next;
  const Icon = cfg.icon;

  return (
    <div
      style={{
        background: "#fff",
        border: `2px solid ${cfg.color}`,
        borderRadius: 12,
        padding: isCompact ? "8px 12px" : "14px 18px",
        minWidth: isCompact ? 100 : 180,
        boxShadow: status === "current" ? `0 0 20px ${cfg.color}30` : "0 2px 8px rgba(0,0,0,0.06)",
        transition: "all 0.3s ease",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: cfg.color, width: 8, height: 8 }} />

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: isCompact ? 0 : 8 }}>
        <Icon
          size={isCompact ? 16 : 20}
          style={{ color: cfg.color, animation: status === "current" ? "spin 1s linear infinite" : "none" }}
        />
        <span style={{ fontWeight: 700, fontSize: isCompact ? 13 : 15, color: "var(--gray-900)" }}>
          {label}
        </span>
        {pause && (
          <span
            style={{
              fontSize: 10,
              background: "var(--gold-light)",
              color: "var(--gold)",
              padding: "1px 6px",
              borderRadius: 4,
              fontWeight: 600,
            }}
          >
            人工审阅
          </span>
        )}
      </div>

      {!isCompact && (
        <>
          <div style={{ fontSize: 12, color: "var(--gray-500)", marginBottom: 4 }}>{agent}</div>
          <div style={{ fontSize: 11, color: "var(--gray-600)", lineHeight: 1.4 }}>{desc}</div>
        </>
      )}

      <Handle type="source" position={Position.Right} style={{ background: cfg.color, width: 8, height: 8 }} />
    </div>
  );
}

// ── QA special node ──────────────────────────────────────────

function QANode({ data }: NodeProps) {
  const { status, desc, isCompact } = data as {
    status: GateStatus;
    desc: string;
    isCompact: boolean;
  };

  const cfg = status === "error"
    ? { icon: AlertCircle, color: "var(--red)" }
    : status === "done"
    ? { icon: CheckCircle2, color: "var(--green)" }
    : { icon: GitBranch, color: "var(--gray-400)" };
  const Icon = cfg.icon;

  return (
    <div
      style={{
        background: status === "error" ? "#fff5f5" : "#fff",
        border: `2px dashed ${cfg.color}`,
        borderRadius: 12,
        padding: isCompact ? "8px 12px" : "12px 16px",
        minWidth: isCompact ? 80 : 150,
        textAlign: "center",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: cfg.color, width: 8, height: 8 }} />

      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
        <Icon size={isCompact ? 14 : 18} style={{ color: cfg.color }} />
        <span style={{ fontWeight: 600, fontSize: isCompact ? 12 : 14, color: "var(--gray-800)" }}>
          质量门
        </span>
      </div>

      {!isCompact && (
        <div style={{ fontSize: 11, color: "var(--gray-500)", marginTop: 4 }}>{desc}</div>
      )}

      {/* Two output handles: pass → export, fail → back to opportunity */}
      <Handle
        type="source"
        position={Position.Right}
        id="pass"
        style={{ background: "var(--green)", width: 8, height: 8, top: "35%" }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="fail"
        style={{ background: "var(--red)", width: 8, height: 8 }}
      />
    </div>
  );
}

// ── Component ────────────────────────────────────────────────

interface WorkflowEditorProps {
  currentGate?: string;
  gateStatuses?: Record<string, GateStatus>;
  isCompact?: boolean;
}

export function WorkflowEditor({
  currentGate = "scope",
  gateStatuses,
  isCompact = false,
}: WorkflowEditorProps) {
  // Determine gate statuses
  const getStatus = useCallback(
    (gateId: string): GateStatus => {
      if (gateStatuses?.[gateId]) return gateStatuses[gateId];
      const currentIdx = GATES.findIndex((g) => g.id === currentGate);
      const gateIdx = GATES.findIndex((g) => g.id === gateId);
      if (currentIdx === -1) return "next";
      if (gateIdx < currentIdx) return "done";
      if (gateIdx === currentIdx) return "current";
      return "next";
    },
    [currentGate, gateStatuses]
  );

  // Build nodes
  const nodes: Node[] = useMemo(() => {
    const spacing = isCompact ? 160 : 240;
    const ySpacing = isCompact ? 80 : 120;

    // Layout: snake pattern for better readability
    const positions = [
      { x: 0, y: 0 },                    // scope
      { x: spacing, y: 0 },              // evidence
      { x: spacing * 2, y: 0 },          // research_frame
      { x: spacing * 2, y: ySpacing },    // knowledge_map (below research_frame)
      { x: spacing, y: ySpacing },        // opportunity (below evidence)
      { x: 0, y: ySpacing },             // qa_critic (below scope)
      { x: 0, y: ySpacing * 2 },         // export (below qa_critic)
    ];

    const gateNodes: Node[] = GATES.map((gate, i) => ({
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
    }));

    return gateNodes;
  }, [getStatus, isCompact]);

  // Build edges
  const edges: Edge[] = useMemo(() => {
    const baseStyle = { strokeWidth: 2 };

    const gateEdges: Edge[] = [
      { id: "e1", source: "scope", target: "evidence", ...baseStyle },
      { id: "e2", source: "evidence", target: "research_frame", ...baseStyle },
      { id: "e3", source: "research_frame", target: "knowledge_map", ...baseStyle },
      { id: "e4", source: "knowledge_map", target: "opportunity", ...baseStyle },
      { id: "e5", source: "opportunity", target: "qa_critic", ...baseStyle },
      { id: "e6", source: "qa_critic", sourceHandle: "pass", target: "export", ...baseStyle, label: "通过" },
      { id: "e7", source: "qa_critic", sourceHandle: "fail", target: "opportunity", style: { ...baseStyle, stroke: "var(--red)", strokeDasharray: "5,5" }, label: "回退" },
    ];

    // Color edges based on gate status
    return gateEdges.map((edge) => {
      const sourceStatus = getStatus(edge.source);
      const isActive = sourceStatus === "done" || sourceStatus === "current";
      return {
        ...edge,
        style: {
          ...edge.style,
          stroke: isActive ? (edge.id === "e7" ? "var(--red)" : "var(--green)") : "var(--gray-300)",
        },
        animated: sourceStatus === "current",
      };
    });
  }, [getStatus]);

  const nodeTypes: NodeTypes = useMemo(
    () => ({ gateNode: GateNode, qaNode: QANode }),
    []
  );

  return (
    <div style={{ width: "100%", height: isCompact ? 300 : 500 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable={true}
        nodesConnectable={false}
        elementsSelectable={false}
        minZoom={0.5}
        maxZoom={1.5}
      >
        <Background color="var(--gray-200)" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
