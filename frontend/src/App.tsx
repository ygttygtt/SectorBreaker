import { useCallback, useEffect, useRef, useState } from "react";
import gsap from "gsap";
import {
  Play,
  Loader2,
  CheckCircle2,
  Download,
  Search,
  Settings,
  ArrowLeft,
  FileText,
  Database,
  Zap,
} from "lucide-react";

import "./styles.css";
import { ToastContainer, useToast } from "./components/Toast";
import { ConfigPanel } from "./components/ConfigPanel";
import { Logo } from "./components/Logo";
import { GraphFlow, GATES } from "./components/GraphFlow";
import { LogStream } from "./components/LogStream";
import { DebugPanel } from "./components/DebugPanel";
import { WorkflowEditor } from "./components/WorkflowEditor";
import { ReviewView } from "./components/ReviewView";
import { api } from "./api/client";
import { useRunEvents } from "./hooks/useRunEvents";
import type { Project, RunEvent, Artifact, Evidence, ChatResponse, ExportManifest } from "./api/client";

type AppPhase = "landing" | "researching" | "reviewing" | "result";

/* ================================================================== */
/*  LandingView                                                        */
/* ================================================================== */

function LandingView({ onStart, onOpenSettings, isLoading, llmConfigured }: {
  onStart: (domain: string, autoRun?: boolean) => void;
  onOpenSettings: () => void;
  isLoading: boolean;
  llmConfigured: boolean;
}) {
  const [domain, setDomain] = useState("");
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(".landing-brand", { y: -30, opacity: 0, duration: 0.6, ease: "power2.out" });
      gsap.from(".landing-title", { y: 20, opacity: 0, duration: 0.6, delay: 0.1, ease: "power2.out" });
      gsap.from(".landing-subtitle", { y: 20, opacity: 0, duration: 0.6, delay: 0.2, ease: "power2.out" });
      gsap.from(".landing-form", { y: 20, opacity: 0, duration: 0.6, delay: 0.3, ease: "power2.out" });
      gsap.from(".landing-steps-preview", { y: 20, opacity: 0, duration: 0.6, delay: 0.5, ease: "power2.out" });
    });
    return () => ctx.revert();
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (domain.trim()) onStart(domain.trim());
  }

  return (
    <div className="landing">
      <div className="landing-brand">
        <Logo size={80} />
        <h1>SectorBreaker</h1>
        <p>领 域 破 壁 系 统</p>
      </div>

      <h2 className="landing-title">你想了解什么领域？</h2>
      <p className="landing-subtitle">
        输入一个行业或领域名称，AI 将为你拆解产业链、竞品格局、内容生态和机会地图
      </p>

      {!llmConfigured && (
        <div className="landing-warning" onClick={onOpenSettings}>
          <Settings size={16} />
          <span>LLM 未配置 — 点击此处设置 API 密钥后才能开始研究</span>
        </div>
      )}

      <form ref={formRef} className="landing-form" onSubmit={handleSubmit}>
        <div className="landing-input-wrap">
          <Search size={20} className="landing-input-icon" />
          <input
            className="landing-input"
            type="text"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="例如：AI Agent 工具、本地生活服务、跨境电商…"
            autoFocus
          />
        </div>
        <div className="landing-btn-row">
          <button className="primary landing-btn" type="submit" disabled={!domain.trim() || isLoading || !llmConfigured}>
            {isLoading ? (
              <>
                <Loader2 size={18} className="spinner" />
                启动中…
              </>
            ) : (
              <>
                <Play size={18} />
                开始破壁
              </>
            )}
          </button>
          <button
            className="secondary landing-btn landing-btn--auto"
            type="button"
            disabled={!domain.trim() || isLoading}
            onClick={() => { if (domain.trim()) onStart(domain.trim(), true); }}
          >
            <Zap size={16} />
            一键执行
          </button>
        </div>
      </form>

      <div className="landing-steps-preview">
        <p>研究流程</p>
        <div style={{ height: 280, borderRadius: 12, overflow: "hidden", border: "1px solid var(--gray-200)" }}>
          <WorkflowEditor currentGate="scope" isCompact showControls={false} />
        </div>
      </div>

      <button className="landing-settings" onClick={onOpenSettings} type="button">
        <Settings size={16} />
        LLM 设置
      </button>
    </div>
  );
}

/* ================================================================== */
/*  ResearchView                                                       */
/* ================================================================== */

function ResearchView({
  project, runId, events, activeAgent, activeMessage, isConnected,
  onBack,
}: {
  project: Project;
  runId: string;
  events: RunEvent[];
  activeAgent: string | null;
  activeMessage: string | null;
  isConnected: boolean;
  onBack: () => void;
}) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [showWorkflow, setShowWorkflow] = useState(false);

  useEffect(() => {
    if (!contentRef.current) return;
    const ctx = gsap.context(() => {
      gsap.from(".research-header", { y: -20, opacity: 0, duration: 0.4, ease: "power2.out" });
      gsap.from(".research-info", { y: -10, opacity: 0, duration: 0.4, delay: 0.1, ease: "power2.out" });
      gsap.from(".graph-flow", { y: 20, opacity: 0, duration: 0.5, delay: 0.2, ease: "power2.out" });
      gsap.from(".log-stream", { y: 20, opacity: 0, duration: 0.5, delay: 0.3, ease: "power2.out" });
    }, contentRef);
    return () => ctx.revert();
  }, []);

  const currentGate = events.length > 0
    ? [...events].reverse().find((e) => e.gate)?.gate ?? "scope"
    : "scope";

  const scopeLabel = project.market_scope === "china" ? "中国市场"
    : project.market_scope === "global" ? "全球市场" : "混合市场";

  return (
    <div ref={contentRef} className="research">
      <header className="research-header">
        <div className="research-header-left">
          <Logo size={28} animate={false} />
          <h1>SectorBreaker</h1>
        </div>
        <button className="secondary" onClick={onBack}>
          <ArrowLeft size={16} />
          新研究
        </button>
      </header>

      <div className="research-info">
        <div className="research-domain">
          <strong>{project.domain}</strong>
          <span className="research-scope">{scopeLabel}</span>
        </div>
        {isConnected ? (
          <span className="research-status research-status--running">
            <Loader2 size={14} className="spinner" />
            研究进行中
          </span>
        ) : (
          <span className="research-status research-status--disconnected">
            连接已断开
          </span>
        )}
      </div>

      <div style={{ position: "relative" }}>
        <GraphFlow
          currentGate={currentGate}
          activeAgent={activeAgent}
          activeMessage={activeMessage}
        />
        <button
          className="secondary"
          onClick={() => setShowWorkflow(!showWorkflow)}
          style={{ position: "absolute", top: 8, right: 8, fontSize: 12, padding: "4px 10px" }}
          type="button"
        >
          {showWorkflow ? "收起" : "展开"}工作流图
        </button>
      </div>

      {showWorkflow && (
        <div style={{ borderBottom: "1px solid var(--gray-200)", background: "#fafafa" }}>
          <WorkflowEditor currentGate={currentGate} />
        </div>
      )}

      <LogStream events={events} />
      <DebugPanel events={events} />
    </div>
  );
}

/* ================================================================== */
/*  ResultView                                                         */
/* ================================================================== */

function ResultView({
  project, artifacts, evidence, chat, setChat, exportManifest, setExportManifest,
  onNewResearch, toastError, toastSuccess,
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
  const [selectedGate, setSelectedGate] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!contentRef.current) return;
    const ctx = gsap.context(() => {
      gsap.from(".result-header", { y: -20, opacity: 0, duration: 0.4, ease: "power2.out" });
      gsap.from(".graph-flow", { y: 20, opacity: 0, duration: 0.5, delay: 0.1, ease: "power2.out" });
      gsap.from(".result-section", {
        y: 20, opacity: 0, duration: 0.4, stagger: 0.1, delay: 0.2, ease: "power2.out",
      });
    }, contentRef);
    return () => ctx.revert();
  }, []);

  async function askQuestion() {
    if (!question.trim()) return;
    try {
      const response = await api.askQuestion(project.id, question);
      setChat(response);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "问答请求失败");
    }
  }

  async function exportProject() {
    setIsExporting(true);
    try {
      const manifest = await api.exportProject(project.id);
      setExportManifest(manifest);
      toastSuccess("导出成功！");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "导出失败");
    } finally {
      setIsExporting(false);
    }
  }

  const displayArtifacts = selectedGate
    ? artifacts.filter((a) => a.id.toLowerCase().includes(selectedGate.replace("_", "-")))
    : artifacts;

  return (
    <div ref={contentRef} className="result">
      <header className="result-header">
        <div className="result-header-left">
          <Logo size={28} animate={false} />
          <h1>SectorBreaker</h1>
        </div>
        <div className="result-header-right">
          <span className="result-status">
            <CheckCircle2 size={16} />
            研究完成
          </span>
          <button className="secondary" onClick={onNewResearch}>
            <Play size={16} />
            新研究
          </button>
        </div>
      </header>

      <div className="result-info">
        <strong>{project.domain}</strong>
      </div>

      <GraphFlow
        currentGate="export"
        onGateClick={(gate) => setSelectedGate(selectedGate === gate ? null : gate)}
      />

      <div style={{ padding: "0 32px", background: "#fafafa", borderBottom: "1px solid var(--gray-200)" }}>
        <WorkflowEditor currentGate="export" isCompact />
      </div>

      <div className="result-content">
        <section className="result-section">
          <div className="result-section-title">
            <FileText size={18} />
            <h3>{selectedGate ? `${GATES.find((g) => g.key === selectedGate)?.name ?? ""} 产物` : "全部产物"}</h3>
          </div>
          {displayArtifacts.length > 0 ? (
            <ul className="result-artifact-list">
              {displayArtifacts.map((a) => (
                <li key={a.id}>
                  <FileText size={14} />
                  <span className="artifact-name">{a.title || a.id}</span>
                  <span className="artifact-path">{a.content_path}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="result-empty">该阶段暂无产物</p>
          )}
        </section>

        <section className="result-section">
          <div className="result-section-title">
            <Database size={18} />
            <h3>证据来源 ({evidence.length})</h3>
          </div>
          {evidence.length > 0 ? (
            <ul className="result-evidence-list">
              {evidence.map((ev) => (
                <li key={ev.id}>
                  <strong>{ev.source_title}</strong>
                  <p>{ev.snippet}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="result-empty">暂无证据</p>
          )}
        </section>

        <section className="result-section result-section--chat">
          <div className="result-section-title">
            <Search size={18} />
            <h3>项目问答</h3>
          </div>
          <div className="result-chat-row">
            <input
              aria-label="项目问题"
              placeholder="基于当前研究继续追问"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && askQuestion()}
            />
            <button className="primary" type="button" onClick={askQuestion} disabled={!question.trim()}>
              询问
            </button>
          </div>
          {chat && (
            <div className="result-chat-answer">
              <p>{chat.answer}</p>
              <span>引用：{chat.citations.join(", ")}</span>
            </div>
          )}
        </section>

        <section className="result-section result-section--export">
          <button className="primary" onClick={exportProject} disabled={isExporting}>
            {isExporting ? (
              <>
                <Loader2 size={18} className="spinner" />
                导出中…
              </>
            ) : (
              <>
                <Download size={18} />
                导出知识库
              </>
            )}
          </button>
          {exportManifest && (
            <p className="result-export-info">
              已导出 {exportManifest.artifact_paths.length} 个文件
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  App                                                                */
/* ================================================================== */

export function App() {
  const { toasts, removeToast, success, error } = useToast();

  const [phase, setPhase] = useState<AppPhase>("landing");
  const [project, setProject] = useState<Project | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [chat, setChat] = useState<ChatResponse | null>(null);
  const [exportManifest, setExportManifest] = useState<ExportManifest | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [activeMessage, setActiveMessage] = useState<string | null>(null);
  const [reviewingGate, setReviewingGate] = useState<string | null>(null);
  const [reviewingEvents, setReviewingEvents] = useState<RunEvent[]>([]);
  const [llmConfigured, setLlmConfigured] = useState(true); // Assume configured until check fails

  // Check LLM config on mount
  useEffect(() => {
    api.getLLMConfig().then((cfg) => {
      setLlmConfigured(cfg.configured);
    }).catch(() => setLlmConfigured(false));
  }, []);


  // SSE event handlers
  const onEvent = useCallback((event: RunEvent) => {
    setActiveAgent(event.agent ?? null);
    setActiveMessage(event.message);
  }, []);

  const onComplete = useCallback(async () => {
    if (!project || !runId) return;
    try {
      // Fetch run status to determine which gate we're at
      const run = await api.getRun(runId);
      const [artifactsData, evidenceData] = await Promise.all([
        api.listArtifacts(project.id),
        api.listEvidence(project.id),
      ]);
      setArtifacts(artifactsData);
      setEvidence(evidenceData);

      // Always set to reviewing — the waiting_for_human effect may have
      // already done this, but setting it again is idempotent
      setReviewingGate(run.current_gate || "export");
      setPhase("reviewing");
    } catch {
      error("获取研究结果失败");
    }
  }, [project, runId, error]);

  // Handle waiting_for_human events — show review for specific gate
  const onWaitingForHuman = useCallback((event: RunEvent) => {
    setReviewingGate(event.gate);
    setPhase("reviewing");
  }, []);

  const onError = useCallback((msg: string) => {
    error(msg);
  }, [error]);

  const { events, isConnected, reset: resetEvents } = useRunEvents({
    runId,
    onEvent,
    onComplete,
    onError,
  });

  // Detect waiting_for_human events from the event stream
  useEffect(() => {
    const waitingEvent = events.find((e) => e.event_type === "waiting_for_human");
    if (waitingEvent && phase === "researching") {
      setReviewingGate(waitingEvent.gate);
      // Collect events for this gate
      const gateEvents = events.filter((e) => e.gate === waitingEvent.gate);
      setReviewingEvents(gateEvents);
      setPhase("reviewing");
    }
  }, [events, phase]);

  async function startResearch(domain: string, autoRun: boolean = false) {
    setIsLoading(true);
    setChat(null);
    setExportManifest(null);
    setActiveAgent(null);
    setActiveMessage(null);
    setReviewingGate(null);
    setReviewingEvents([]);

    // Timeout safety: if still loading after 120s, unlock the button
    const timeout = setTimeout(() => setIsLoading(false), 120000);

    try {
      const proj = await api.createProject({
        title: domain,
        domain,
        market_scope: "mixed",
        depth: "quick",
      });
      setProject(proj);

      const run = await api.startRun(proj.id, autoRun);
      setRunId(run.id);
      setPhase("researching");
    } catch (err) {
      const message = err instanceof Error ? err.message : "启动研究失败";
      error(message);
      setPhase("landing");
    } finally {
      clearTimeout(timeout);
      setIsLoading(false);
    }
  }

  function resetToLanding() {
    setPhase("landing");
    setProject(null);
    setRunId(null);
    setArtifacts([]);
    setEvidence([]);
    setChat(null);
    setExportManifest(null);
    setActiveAgent(null);
    setActiveMessage(null);
    setReviewingGate(null);
    setReviewingEvents([]);
    resetEvents();
  }

  // Resume workflow after human review
  async function handleReviewContinue(guidance?: string, evidenceData?: string) {
    if (!runId) return;
    try {
      await api.resumeRun(runId, {
        guidance: guidance || undefined,
        evidence_data: evidenceData || undefined,
      });
      setPhase("researching");
      setReviewingGate(null);
      setReviewingEvents([]);
      success("已继续研究");
    } catch (err) {
      error(err instanceof Error ? err.message : "恢复研究失败");
    }
  }

  async function handleReviewSkip() {
    if (!runId) return;
    try {
      await api.resumeRun(runId, {});
      setPhase("researching");
      setReviewingGate(null);
      setReviewingEvents([]);
    } catch (err) {
      error(err instanceof Error ? err.message : "恢复研究失败");
    }
  }

  // Handle final review (after all gates complete)
  async function handleFinalContinue(guidance?: string, evidenceData?: string) {
    if (guidance || evidenceData) {
      success("已保存补充信息，研究完成！");
    }
    setPhase("result");
  }

  function handleFinalSkip() {
    setPhase("result");
    success("研究完成！");
  }

  // Check if this is the final review (export gate) or intermediate
  const isFinalReview = reviewingGate === "export";

  return (
    <main className="shell">
      <ToastContainer toasts={toasts} onRemove={removeToast} />
      <ConfigPanel
        isOpen={showConfig}
        onClose={() => setShowConfig(false)}
        onSuccess={success}
        onError={error}
      />

      {phase === "landing" && (
        <LandingView
          onStart={startResearch}
          onOpenSettings={() => setShowConfig(true)}
          isLoading={isLoading}
          llmConfigured={llmConfigured}
        />
      )}

      {phase === "researching" && project && (
        <ResearchView
          project={project}
          runId={runId ?? ""}
          events={events}
          activeAgent={activeAgent}
          activeMessage={activeMessage}
          isConnected={isConnected}
          onBack={resetToLanding}
        />
      )}

      {phase === "reviewing" && project && runId && (
        <ReviewView
          project={project}
          runId={runId}
          completedGate={reviewingGate ?? "export"}
          events={isFinalReview ? events : reviewingEvents}
          artifacts={isFinalReview ? artifacts : []}
          evidence={isFinalReview ? evidence : []}
          onContinue={isFinalReview ? handleFinalContinue : handleReviewContinue}
          onSkip={isFinalReview ? handleFinalSkip : handleReviewSkip}
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
