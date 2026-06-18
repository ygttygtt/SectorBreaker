import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  FileText,
  Loader2,
  Network,
  Play,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";

import "./styles.css";
import { ToastContainer, useToast } from "./components/Toast";
import { ConfigPanel } from "./components/ConfigPanel";
import { Logo } from "./components/Logo";
import { LogStream } from "./components/LogStream";
import { WorkflowEditor, type NodeStatus } from "./components/WorkflowEditor";
import { api } from "./api/client";
import { useRunEvents } from "./hooks/useRunEvents";
import type {
  Artifact,
  ChatResponse,
  Evidence,
  ExportManifest,
  Project,
  RunEvent,
  SupervisorPlan,
  WorkflowDefinition,
  WorkflowNode,
} from "./api/client";

type AppPhase = "landing" | "researching" | "reviewing" | "result";

const sourcePolicies = [
  { value: "reliable_first", label: "可靠优先", desc: "先查公开可靠源，不足再补开放网络。" },
  { value: "open_web", label: "开放网络", desc: "覆盖更广，噪音更高，关键结论会评级。" },
  { value: "reliable_only", label: "严格可靠", desc: "只允许政府、公告、公开数据库等可靠来源。" },
  { value: "user_materials_only", label: "仅用户材料", desc: "只整理你给的资料，不主动开放搜索。" },
];

const eventNodeMap: Record<string, string> = {
  scope: "scope",
  supervisor_plan: "supervisor_plan",
  source_strategy: "source_strategy",
  evidence: "source_intake",
  claim_extractor: "claim_extractor",
  counterevidence: "counterevidence",
  evidence_ledger: "evidence_ledger",
  knowledge_map: "business_database",
  qa_critic: "qa_critic",
  export: "export",
};

function extractPlan(events: RunEvent[]): SupervisorPlan | null {
  const event = [...events].reverse().find((item) => item.gate === "supervisor_plan" && item.data);
  return (event?.data as unknown as SupervisorPlan) ?? null;
}

function extractQa(events: RunEvent[]) {
  return [...events].reverse().find((item) => item.gate === "qa_critic" && item.data)?.data ?? null;
}

function deriveStatuses(events: RunEvent[]): Record<string, NodeStatus> {
  const statuses: Record<string, NodeStatus> = {};
  for (const event of events) {
    const nodeId = eventNodeMap[event.gate] ?? event.step ?? event.agent?.toLowerCase().replace(/\s+/g, "_");
    if (!nodeId) continue;
    if (event.event_type === "node_started" || event.event_type === "node_progress") statuses[nodeId] = "running";
    if (event.event_type === "node_completed") statuses[nodeId] = "completed";
    if (event.event_type === "node_skipped") statuses[nodeId] = "skipped";
    if (event.event_type === "node_degraded") statuses[nodeId] = "degraded";
    if (event.event_type === "node_blocked") statuses[nodeId] = "blocked";
    if (event.event_type === "node_failed" || event.event_type === "error") statuses[nodeId] = "failed";
    if (event.event_type === "human_input_required" || event.event_type === "waiting_for_human") statuses[nodeId] = "waiting_for_user";
  }
  return statuses;
}

function formatElapsed(startedAt: number | null) {
  if (!startedAt) return "00:00";
  const total = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const min = String(Math.floor(total / 60)).padStart(2, "0");
  const sec = String(total % 60).padStart(2, "0");
  return `${min}:${sec}`;
}

function LandingView({
  onStart,
  onOpenSettings,
  isLoading,
  llmConfigured,
}: {
  onStart: (domain: string, sourcePolicy: string, assistantBrief: string, autoRun?: boolean) => void;
  onOpenSettings: () => void;
  isLoading: boolean;
  llmConfigured: boolean;
}) {
  const [domain, setDomain] = useState("");
  const [sourcePolicy, setSourcePolicy] = useState("reliable_first");
  const [assistantBrief, setAssistantBrief] = useState("");
  const [showBrief, setShowBrief] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const ctx = gsap.context(() => {
      gsap.from(".landing-panel", { y: 18, autoAlpha: 0, duration: 0.45, stagger: 0.08, ease: "power2.out" });
    }, containerRef);
    return () => ctx.revert();
  }, []);

  function submit(autoRun = false) {
    if (!domain.trim()) return;
    onStart(domain.trim(), sourcePolicy, assistantBrief.trim(), autoRun);
  }

  return (
    <div ref={containerRef} className="landing-pro">
      <section className="landing-panel landing-panel--main">
        <div className="landing-brand">
          <Logo size={44} />
          <div>
            <h1>SectorBreaker</h1>
            <p>可解释多 Agent 商业情报系统</p>
          </div>
        </div>
        <div className="landing-copy">
          <h2>先建立证据账本，再生成行业认知。</h2>
          <p>主管 Agent 会先给出研究计划，确认后再调度搜索、证据、商业分析和质检节点。</p>
        </div>
        {!llmConfigured && (
          <button className="landing-warning" onClick={onOpenSettings} type="button">
            <Settings size={16} />
            LLM 未配置，点击设置 API 密钥
          </button>
        )}
        <label className="field-label" htmlFor="domain">研究领域</label>
        <div className="landing-input-wrap">
          <Search size={18} className="landing-input-icon" />
          <input
            id="domain"
            className="landing-input"
            value={domain}
            onChange={(event) => setDomain(event.target.value)}
            placeholder="例如：编程教育、本地生活服务、AI Agent 工具"
            autoFocus
          />
        </div>
        <div className="source-policy-grid">
          {sourcePolicies.map((item) => (
            <button
              key={item.value}
              className={`source-policy-card ${sourcePolicy === item.value ? "source-policy-card--active" : ""}`}
              onClick={() => setSourcePolicy(item.value)}
              type="button"
            >
              <strong>{item.label}</strong>
              <span>{item.desc}</span>
            </button>
          ))}
        </div>
        <button className="brief-toggle" type="button" onClick={() => setShowBrief((value) => !value)}>
          <Sparkles size={15} />
          {showBrief ? "收起外部 AI 报告" : "可选：粘贴 Gemini / Kimi / Qwen / DeepSeek 报告"}
        </button>
        {showBrief && (
          <textarea
            className="assistant-brief-input"
            value={assistantBrief}
            onChange={(event) => setAssistantBrief(event.target.value)}
            placeholder="支持 Markdown / txt。系统会把它拆成低可信线索，不会直接当事实。"
            rows={7}
          />
        )}
        <div className="landing-actions">
          <button className="primary" disabled={!domain.trim() || isLoading || !llmConfigured} onClick={() => submit(false)} type="button">
            {isLoading ? <Loader2 size={16} className="spinner" /> : <Play size={16} />}
            生成计划
          </button>
          <button className="secondary" disabled={!domain.trim() || isLoading || !llmConfigured} onClick={() => submit(true)} type="button">
            <ShieldCheck size={16} />
            一键执行
          </button>
          <button className="secondary" onClick={onOpenSettings} type="button">
            <Settings size={16} />
            LLM 设置
          </button>
        </div>
      </section>
      <aside className="landing-panel landing-panel--flow">
        <div className="panel-title">
          <Network size={16} />
          <span>真实运行图</span>
        </div>
        <WorkflowEditor isCompact showControls={false} />
      </aside>
    </div>
  );
}

function ResearchView({
  project,
  runId,
  events,
  activeAgent,
  activeMessage,
  workflowDefinition,
  onWorkflowDefinition,
  isConnected,
  onBack,
}: {
  project: Project;
  runId: string;
  events: RunEvent[];
  activeAgent: string | null;
  activeMessage: string | null;
  workflowDefinition: WorkflowDefinition | null;
  onWorkflowDefinition: (definition: WorkflowDefinition) => void;
  isConnected: boolean;
  onBack: () => void;
}) {
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null);
  const [startedAt] = useState(Date.now());
  const [elapsed, setElapsed] = useState("00:00");
  const statuses = useMemo(() => deriveStatuses(events), [events]);
  const latest = events[events.length - 1];
  const activeNodeId = latest ? eventNodeMap[latest.gate] : "scope";
  const evidenceEvents = events.filter((event) => event.event_type === "evidence_collected").length;
  const qaEvent = extractQa(events);

  useEffect(() => {
    if (!runId) return;
    api.getRunWorkflowDefinition(runId).then(onWorkflowDefinition).catch(() => {});
  }, [onWorkflowDefinition, runId, events.length]);

  useEffect(() => {
    const timer = window.setInterval(() => setElapsed(formatElapsed(startedAt)), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  return (
    <div className="workbench">
      <header className="workbench-topbar">
        <div className="topbar-brand">
          <Logo size={24} animate={false} />
          <strong>SectorBreaker</strong>
        </div>
        <div className="topbar-project">
          <span>{project.domain}</span>
          <b>{sourcePolicies.find((p) => p.value === project.source_policy)?.label ?? project.source_policy}</b>
        </div>
        <div className="topbar-status">
          <span className={`run-pill ${isConnected ? "run-pill--live" : ""}`}>
            {isConnected ? <Loader2 size={13} className="spinner" /> : <Clock3 size={13} />}
            {isConnected ? "实时连接" : "等待事件"}
          </span>
          <span className="run-time">{elapsed}</span>
          <button className="secondary btn-sm" onClick={onBack} type="button">
            <ArrowLeft size={14} />
            新研究
          </button>
        </div>
      </header>
      <div className="workbench-grid">
        <aside className="workbench-left">
          <div className="panel-title">
            <Network size={15} />
            <span>运行图</span>
          </div>
          <WorkflowEditor
            definition={workflowDefinition}
            activeNodeId={activeNodeId}
            nodeStatuses={statuses}
            onNodeClick={setSelectedNode}
            showMinimap
            fillHeight
          />
        </aside>
        <main className="workbench-center">
          <section className="agent-focus-card">
            <div className="agent-focus-head">
              <span>{activeAgent ?? "等待 Agent"}</span>
              {latest?.severity === "error" ? <AlertTriangle size={18} /> : <Loader2 size={18} className={isConnected ? "spinner" : ""} />}
            </div>
            <p>{activeMessage ?? "准备生成主管计划与证据账本。"}</p>
            {latest?.progress_total ? (
              <div className="progress-line">
                <span style={{ width: `${Math.min(100, ((latest.progress_current ?? 0) / latest.progress_total) * 100)}%` }} />
              </div>
            ) : (
              <div className="heartbeat-line" />
            )}
          </section>
          <section className="metrics-strip">
            <div>
              <strong>{events.length}</strong>
              <span>事件</span>
            </div>
            <div>
              <strong>{evidenceEvents}</strong>
              <span>证据事件</span>
            </div>
            <div>
              <strong>{Object.values(statuses).filter((value) => value === "completed").length}</strong>
              <span>完成节点</span>
            </div>
            <div>
              <strong>{Object.values(statuses).filter((value) => value === "blocked").length}</strong>
              <span>阻塞</span>
            </div>
          </section>
          {selectedNode && (
            <section className="node-detail-card">
              <button className="node-detail-close" onClick={() => setSelectedNode(null)} type="button">
                <X size={15} />
              </button>
              <h3>{selectedNode.label}</h3>
              <p>{selectedNode.reason || "该节点用于呈现真实后台执行状态。"}</p>
              <dl>
                <dt>类型</dt><dd>{selectedNode.node_type}</dd>
                <dt>分组</dt><dd>{selectedNode.group}</dd>
                <dt>Agent</dt><dd>{selectedNode.agent_id ?? "-"}</dd>
              </dl>
            </section>
          )}
          {qaEvent && (
            <section className="qa-warning-card">
              <AlertTriangle size={18} />
              <div>
                <strong>质量门提示</strong>
                <p>{JSON.stringify(qaEvent).slice(0, 220)}</p>
              </div>
            </section>
          )}
        </main>
        <aside className="workbench-right">
          <div className="panel-title">
            <FileText size={15} />
            <span>研究事件流</span>
          </div>
          <LogStream events={events} />
        </aside>
      </div>
    </div>
  );
}

function ReviewView({
  project,
  runId,
  completedGate,
  events,
  artifacts,
  evidence,
  onContinue,
  onSkip,
}: {
  project: Project;
  runId: string;
  completedGate: string;
  events: RunEvent[];
  artifacts: Artifact[];
  evidence: Evidence[];
  onContinue: (guidance?: string, evidenceData?: string, assistantBrief?: string) => void;
  onSkip: () => void;
}) {
  const [guidance, setGuidance] = useState("");
  const [evidenceData, setEvidenceData] = useState("");
  const [assistantBrief, setAssistantBrief] = useState("");
  const plan = extractPlan(events);
  const qa = extractQa(events);
  const isPlanReview = completedGate === "supervisor_plan";
  const isQaBlocked = Boolean(qa);

  return (
    <div className="review-pro">
      <header className="review-pro-header">
        <div>
          <Logo size={24} animate={false} />
          <strong>{isPlanReview ? "确认主管计划" : isQaBlocked ? "质量门需要处理" : "阶段审阅"}</strong>
        </div>
        <span>{project.domain}</span>
      </header>
      <main className="review-pro-grid">
        <section className="review-pro-main">
          {plan && (
            <div className="plan-card">
              <h2>{plan.intent_summary}</h2>
              <p className="muted">{plan.source_policy_reason}</p>
              <div className="plan-section">
                <h3>启用 Agent</h3>
                <div className="agent-chip-grid">
                  {plan.selected_agents.map((agent) => (
                    <div className="agent-chip" key={agent.agent_id}>
                      <strong>{agent.display_name}</strong>
                      <span>{agent.reason}</span>
                      <em>{agent.run_mode} / {agent.verification_level}</em>
                    </div>
                  ))}
                </div>
              </div>
              <div className="plan-section">
                <h3>跳过 Agent</h3>
                <ul className="compact-list">
                  {plan.skipped_agents.map((agent) => <li key={agent.agent_id}>{agent.display_name}：{agent.reason}</li>)}
                </ul>
              </div>
              <div className="plan-section">
                <h3>重点验证</h3>
                <ul className="compact-list">
                  {plan.verification_plan.counterevidence_triggers.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            </div>
          )}
          {qa && (
            <div className="qa-block-card">
              <AlertTriangle size={20} />
              <div>
                <h2>QA 阻塞</h2>
                <pre>{JSON.stringify(qa, null, 2)}</pre>
              </div>
            </div>
          )}
          {!plan && !qa && (
            <div className="plan-card">
              <h2>阶段完成</h2>
              <p>已生成 {artifacts.length} 个产物，收集 {evidence.length} 条证据。</p>
            </div>
          )}
        </section>
        <aside className="review-pro-side">
          <label>研究方向补充</label>
          <textarea value={guidance} onChange={(e) => setGuidance(e.target.value)} rows={4} placeholder="只需要补方向、边界、偏好；资料查证仍由系统负责。" />
          <label>用户材料</label>
          <textarea value={evidenceData} onChange={(e) => setEvidenceData(e.target.value)} rows={5} placeholder="可粘贴你已有的笔记、链接、报告摘要。" />
          {isPlanReview && (
            <>
              <label>外部 AI 报告（可选）</label>
              <textarea value={assistantBrief} onChange={(e) => setAssistantBrief(e.target.value)} rows={7} placeholder="Markdown / txt。仅作为线索，不能单独支撑事实。" />
            </>
          )}
          <div className="review-actions">
            <button className="secondary" onClick={onSkip} type="button">跳过补充</button>
            <button className="primary" onClick={() => onContinue(guidance, evidenceData, assistantBrief)} type="button">
              <CheckCircle2 size={16} />
              确认并继续
            </button>
          </div>
        </aside>
      </main>
    </div>
  );
}

function ResultView({
  project,
  artifacts,
  evidence,
  chat,
  setChat,
  exportManifest,
  setExportManifest,
  onNewResearch,
  toastError,
  toastSuccess,
}: {
  project: Project;
  artifacts: Artifact[];
  evidence: Evidence[];
  chat: ChatResponse | null;
  setChat: (c: ChatResponse | null) => void;
  exportManifest: ExportManifest | null;
  setExportManifest: (m: ExportManifest | null) => void;
  onNewResearch: () => void;
  toastError: (msg: string) => void;
  toastSuccess: (msg: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const [isExporting, setIsExporting] = useState(false);

  async function askQuestion() {
    if (!question.trim()) return;
    try {
      setChat(await api.askQuestion(project.id, question));
    } catch (err) {
      toastError(err instanceof Error ? err.message : "问答请求失败");
    }
  }

  async function exportProject() {
    setIsExporting(true);
    try {
      const manifest = await api.exportProject(project.id);
      setExportManifest(manifest);
      toastSuccess("导出成功");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "导出失败");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="result-pro">
      <header className="workbench-topbar">
        <div className="topbar-brand"><Logo size={24} animate={false} /><strong>SectorBreaker</strong></div>
        <div className="topbar-project"><span>{project.domain}</span><b>研究完成</b></div>
        <button className="secondary btn-sm" onClick={onNewResearch} type="button"><Play size={14} />新研究</button>
      </header>
      <main className="result-pro-grid">
        <section className="result-card">
          <h3><FileText size={16} />产物</h3>
          <ul className="result-artifact-list">
            {artifacts.map((item) => <li key={item.id}><span>{item.title}</span><em>{item.content_path}</em></li>)}
          </ul>
        </section>
        <section className="result-card">
          <h3><Database size={16} />证据账本</h3>
          <ul className="result-evidence-list">
            {evidence.map((item) => (
              <li key={item.id}>
                <strong>{item.source_title}</strong>
                <p>{item.snippet}</p>
                <span>{item.source_quality ?? "unknown"} / {item.verification_status ?? "unverified"}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="result-card result-card--wide">
          <h3><Search size={16} />项目问答</h3>
          <div className="result-chat-row">
            <input value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === "Enter" && askQuestion()} placeholder="基于证据账本继续追问" />
            <button className="primary btn-sm" onClick={askQuestion} disabled={!question.trim()} type="button">询问</button>
            <button className="secondary btn-sm" onClick={exportProject} disabled={isExporting} type="button">
              {isExporting ? <Loader2 size={14} className="spinner" /> : <Download size={14} />}
              导出
            </button>
          </div>
          {chat && <p className="chat-answer">{chat.answer} 引用：{chat.citations.join(", ")}</p>}
          {exportManifest && <p className="chat-answer">已导出 {exportManifest.artifact_paths.length} 个文件。</p>}
        </section>
      </main>
    </div>
  );
}

export function App() {
  const { toasts, removeToast, success, error } = useToast();
  const [phase, setPhase] = useState<AppPhase>("landing");
  const [project, setProject] = useState<Project | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [workflowDefinition, setWorkflowDefinition] = useState<WorkflowDefinition | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [chat, setChat] = useState<ChatResponse | null>(null);
  const [exportManifest, setExportManifest] = useState<ExportManifest | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [activeMessage, setActiveMessage] = useState<string | null>(null);
  const [reviewingGate, setReviewingGate] = useState<string | null>(null);
  const [llmConfigured, setLlmConfigured] = useState(true);

  useEffect(() => {
    api.getLLMConfig().then((cfg) => setLlmConfigured(cfg.configured)).catch(() => setLlmConfigured(false));
  }, []);

  const onEvent = useCallback((event: RunEvent) => {
    setActiveAgent(event.agent ?? null);
    setActiveMessage(event.message);
  }, []);

  const onComplete = useCallback(async () => {
    if (!project || !runId) return;
    try {
      const run = await api.getRun(runId);
      const [artifactData, evidenceData] = await Promise.all([api.listArtifacts(project.id), api.listEvidence(project.id)]);
      setArtifacts(artifactData);
      setEvidence(evidenceData);
      setReviewingGate(run.current_gate || "export");
      setPhase("reviewing");
    } catch {
      error("获取研究结果失败");
    }
  }, [error, project, runId]);

  const { events, isConnected, reset: resetEvents } = useRunEvents({ runId, onEvent, onComplete, onError: error });

  useEffect(() => {
    const waiting = events.find((event) => event.event_type === "waiting_for_human" || event.event_type === "human_input_required");
    if (waiting && phase === "researching") {
      setReviewingGate(waiting.gate);
      setPhase("reviewing");
    }
  }, [events, phase]);

  async function startResearch(domain: string, sourcePolicy: string, assistantBrief: string, autoRun = false) {
    setIsLoading(true);
    try {
      const proj = await api.createProject({ title: domain, domain, market_scope: "mixed", depth: "quick", source_policy: sourcePolicy });
      setProject(proj);
      const run = await api.startRun(proj.id, autoRun);
      setRunId(run.id);
      setPhase("researching");
      if (assistantBrief && !autoRun) {
        // The user can still edit it on the plan confirmation screen; keep this UX non-blocking.
        success("外部报告已准备，可在计划确认页再次确认。");
      }
      if (assistantBrief && autoRun) {
        await api.resumeRun(run.id, { assistant_brief: assistantBrief, plan_confirmed: true }).catch(() => {});
      }
    } catch (err) {
      error(err instanceof Error ? err.message : "启动研究失败");
    } finally {
      setIsLoading(false);
    }
  }

  function resetToLanding() {
    setPhase("landing");
    setProject(null);
    setRunId(null);
    setWorkflowDefinition(null);
    setArtifacts([]);
    setEvidence([]);
    setChat(null);
    setExportManifest(null);
    setReviewingGate(null);
    resetEvents();
  }

  async function handleReviewContinue(guidance?: string, evidenceData?: string, assistantBrief?: string) {
    if (!runId) return;
    if (reviewingGate === "export") {
      setPhase("result");
      success("研究完成");
      return;
    }
    try {
      await api.resumeRun(runId, {
        guidance: guidance || undefined,
        evidence_data: evidenceData || undefined,
        assistant_brief: assistantBrief || undefined,
        plan_confirmed: true,
      });
      setPhase("researching");
      setReviewingGate(null);
      success("已继续研究");
    } catch (err) {
      error(err instanceof Error ? err.message : "恢复研究失败");
    }
  }

  async function handleReviewSkip() {
    if (reviewingGate === "export") {
      setPhase("result");
      return;
    }
    await handleReviewContinue();
  }

  return (
    <main className="shell">
      <ToastContainer toasts={toasts} onRemove={removeToast} />
      <ConfigPanel isOpen={showConfig} onClose={() => setShowConfig(false)} onSuccess={success} onError={error} />
      {phase === "landing" && (
        <LandingView onStart={startResearch} onOpenSettings={() => setShowConfig(true)} isLoading={isLoading} llmConfigured={llmConfigured} />
      )}
      {phase === "researching" && project && (
        <ResearchView
          project={project}
          runId={runId ?? ""}
          events={events}
          activeAgent={activeAgent}
          activeMessage={activeMessage}
          workflowDefinition={workflowDefinition}
          onWorkflowDefinition={setWorkflowDefinition}
          isConnected={isConnected}
          onBack={resetToLanding}
        />
      )}
      {phase === "reviewing" && project && runId && (
        <ReviewView
          project={project}
          runId={runId}
          completedGate={reviewingGate ?? "export"}
          events={events}
          artifacts={artifacts}
          evidence={evidence}
          onContinue={handleReviewContinue}
          onSkip={handleReviewSkip}
        />
      )}
      {phase === "result" && project && (
        <ResultView
          project={project}
          artifacts={artifacts}
          evidence={evidence}
          chat={chat}
          setChat={setChat}
          exportManifest={exportManifest}
          setExportManifest={setExportManifest}
          onNewResearch={resetToLanding}
          toastError={error}
          toastSuccess={success}
        />
      )}
    </main>
  );
}
