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
    { id: "scope", label: "定义领域边界", node_type: "gate", group: "scope", status: "pending", reason: "明确研究对象、市场范围和学习目标。", details: {} },
    { id: "master_agent", label: "主管节点 / ReAct", node_type: "gate", group: "plan", status: "pending", reason: "理解任务、读取材料、规划工具调用，并决定继续、补搜、降级或中断。", details: {} },
    { id: "external_report_intake", label: "外部报告入库", node_type: "agent", group: "source", status: "pending", reason: "接收 Kimi / Gemini / Qwen 等 DeepSearch 报告，提取材料和引用，作为低可信但真实的输入。", details: {} },
    { id: "source_collection", label: "意图驱动搜索", node_type: "agent", group: "source", status: "pending", reason: "由 Master Agent 生成多维搜索计划，补充概念、趋势、政策、案例和需求资料。", details: {} },
    { id: "evidence_ledger", label: "证据账本", node_type: "store", group: "evidence", status: "pending", reason: "去重、清洗摘要、保留来源链接、证据 ID 和低可信/待验证状态。", details: {} },
    { id: "coverage_evaluation", label: "覆盖充分性判断", node_type: "gate", group: "qa", status: "pending", reason: "按概念、现状、趋势、风险、案例、用户需求和信源质量判断是否需要再搜。", details: {} },
    { id: "knowledge_structuring", label: "LLM 知识建库", node_type: "group", group: "analysis", status: "pending", reason: "在覆盖判断允许后，抽取概念、趋势、架构/方法、学习路径和待验证问题。", details: {} },
    { id: "document_writing", label: "逐文档写作", node_type: "agent", group: "synthesis", status: "pending", reason: "让 LLM 分别写主文档，而不是把搜索结果直接粘进去。", details: {} },
    { id: "artifact_review", label: "详实度审查", node_type: "gate", group: "qa", status: "pending", reason: "检查是否太薄、是否有例子、证据和 Obsidian 链接。", details: {} },
    { id: "export", label: "Obsidian 导出 / RAG", node_type: "agent", group: "export", status: "pending", reason: "写入主文档、知识卡片、证据账本，并支持项目问答。", details: {} },
  ],
  edges: [
    { id: "e1", source: "scope", target: "master_agent", label: "研究目标" },
    { id: "e2", source: "master_agent", target: "external_report_intake", label: "读取上传材料" },
    { id: "e3", source: "master_agent", target: "source_collection", label: "规划搜索工具" },
    { id: "e4", source: "external_report_intake", target: "evidence_ledger", label: "报告证据" },
    { id: "e5", source: "source_collection", target: "evidence_ledger", label: "搜索证据" },
    { id: "e6", source: "evidence_ledger", target: "coverage_evaluation", label: "覆盖检查" },
    { id: "e7", source: "coverage_evaluation", target: "master_agent", label: "缺口补搜 / 降级决策" },
    { id: "e8", source: "coverage_evaluation", target: "knowledge_structuring", label: "允许建库" },
    { id: "e9", source: "knowledge_structuring", target: "document_writing" },
    { id: "e10", source: "document_writing", target: "artifact_review" },
    { id: "e11", source: "artifact_review", target: "export" },
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
