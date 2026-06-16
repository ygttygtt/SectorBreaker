import { useState } from "react";
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Circle,
  ClipboardCheck,
  Database,
  Download,
  FileText,
  Loader2,
  Map,
  Play,
  Search,
  Settings,
  ShieldCheck,
  Target,
  UserCheck,
} from "lucide-react";

import "./styles.css";
import { ToastContainer, useToast } from "./components/Toast";
import { ConfigPanel } from "./components/ConfigPanel";

type Project = {
  id: string;
  title: string;
  domain: string;
  market_scope: string;
  depth: string;
};

type Artifact = {
  id: string;
  title: string;
  content_path: string;
  artifact_type?: string;
};

type Evidence = {
  id: string;
  source_title: string;
  snippet: string;
};

type ResearchState = {
  current_gate: string;
  artifacts: Artifact[];
  evidence?: Evidence[];
  qa_issues?: string[];
};

type ChatResponse = {
  answer: string;
  citations: string[];
};

type ExportManifest = {
  artifact_paths: string[];
  evidence_ids: string[];
};

/**
 * 6 fixed gates from the architecture.
 * `humanReview` marks gates that pause for user confirmation.
 */
const gateLabels = [
  { key: "scope", name: "范围确认", icon: Target, humanReview: true },
  { key: "research_frame", name: "研究框架", icon: ClipboardCheck, humanReview: true },
  { key: "evidence", name: "资料证据", icon: Database, humanReview: false },
  { key: "knowledge_map", name: "知识地图", icon: Map, humanReview: false },
  { key: "opportunity", name: "机会地图", icon: Search, humanReview: true },
  { key: "export", name: "知识库导出", icon: Download, humanReview: false },
];

type AppPhase = "landing" | "running" | "done";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(error.detail || `API 请求失败: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

/* ------------------------------------------------------------------ */
/*  Gate stepper                                                       */
/* ------------------------------------------------------------------ */

function GateStepper({ currentGate, phase }: { currentGate: string; phase: AppPhase }) {
  const currentIdx = gateLabels.findIndex((g) => g.key === currentGate);

  return (
    <div className="stepper">
      {gateLabels.map((gate, idx) => {
        let status: "done" | "current" | "next" = "next";
        if (phase === "done") status = "done";
        else if (idx < currentIdx) status = "done";
        else if (idx === currentIdx) status = "current";

        const Icon = gate.icon;
        return (
          <div className={`step step--${status}`} key={gate.key}>
            <div className="step-indicator">
              {status === "done" ? (
                <CheckCircle2 size={20} />
              ) : status === "current" ? (
                <Loader2 size={20} className="spinner" />
              ) : (
                <Circle size={20} />
              )}
            </div>
            <div className="step-body">
              <span className="step-label">{gate.name}</span>
              {gate.humanReview && (
                <span className="step-badge">
                  <UserCheck size={12} />
                  人工确认
                </span>
              )}
            </div>
            {idx < gateLabels.length - 1 && <ArrowRight size={14} className="step-arrow" />}
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Landing page                                                       */
/* ------------------------------------------------------------------ */

function LandingPage({ onStart, onOpenSettings, isLoading }: {
  onStart: (domain: string) => void;
  onOpenSettings: () => void;
  isLoading: boolean;
}) {
  const [domain, setDomain] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (domain.trim()) onStart(domain.trim());
  }

  return (
    <div className="landing">
      <div className="landing-brand">
        <Bot size={36} />
        <div>
          <h1>SectorBreaker</h1>
          <p>领域破壁系统</p>
        </div>
      </div>

      <h2 className="landing-title">你想了解什么领域？</h2>
      <p className="landing-subtitle">
        输入一个行业或领域名称，AI 将为你拆解产业链、竞品格局、内容生态和机会地图
      </p>

      <form className="landing-form" onSubmit={handleSubmit}>
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
        <button className="primary landing-btn" type="submit" disabled={!domain.trim() || isLoading}>
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
      </form>

      <div className="landing-steps-preview">
        <p>研究流程</p>
        <div className="landing-steps-row">
          {gateLabels.map((gate, idx) => (
            <div className="landing-step-chip" key={gate.key}>
              <span className="landing-step-num">{idx + 1}</span>
              <span>{gate.name}</span>
              {gate.humanReview && <UserCheck size={12} className="landing-step-hint" />}
            </div>
          ))}
        </div>
      </div>

      <button className="landing-settings" onClick={onOpenSettings} type="button">
        <Settings size={16} />
        LLM 设置
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Research view (running / done)                                     */
/* ------------------------------------------------------------------ */

function ResearchView({
  project, currentGate, phase, artifacts, evidence, qaIssues,
  statusText, question, setQuestion, chat, askQuestion,
  exportManifest, exportProject, onNewResearch,
}: {
  project: Project;
  currentGate: string;
  phase: AppPhase;
  artifacts: Artifact[];
  evidence: Evidence[];
  qaIssues: string[];
  statusText: string;
  question: string;
  setQuestion: (v: string) => void;
  chat: ChatResponse | null;
  askQuestion: () => void;
  exportManifest: ExportManifest | null;
  exportProject: () => void;
  onNewResearch: () => void;
}) {
  return (
    <div className="research">
      {/* Top bar */}
      <header className="research-header">
        <div className="research-header-left">
          <Bot size={22} />
          <h1>SectorBreaker</h1>
        </div>
        <button className="secondary" onClick={onNewResearch}>
          <Play size={16} />
          新研究
        </button>
      </header>

      {/* Project info strip */}
      <div className="research-info">
        <div className="research-domain">
          <Target size={18} />
          <strong>{project.domain}</strong>
        </div>
        <span className="research-scope">{project.market_scope === "china" ? "中国市场" : project.market_scope === "global" ? "全球市场" : "混合市场"}</span>
        <span className={`research-status research-status--${phase}`}>
          {phase === "running" && <Loader2 size={14} className="spinner" />}
          {phase === "done" && <CheckCircle2 size={14} />}
          {statusText}
        </span>
      </div>

      {/* Stepper */}
      <GateStepper currentGate={currentGate} phase={phase} />

      {/* Content area */}
      <div className="research-content">
        {/* Artifacts */}
        <section className="research-section">
          <div className="research-section-title">
            <FileText size={18} />
            <h3>研究产物</h3>
          </div>
          {artifacts.length > 0 ? (
            <ul className="research-artifact-list">
              {artifacts.map((a) => (
                <li key={a.id}>
                  <FileText size={14} />
                  <span className="artifact-name">{a.title || a.id}</span>
                  <span className="artifact-path">{a.content_path}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="research-empty">研究启动后，这里将展示生成的知识卡片和地图</p>
          )}
        </section>

        {/* Evidence */}
        <section className="research-section">
          <div className="research-section-title">
            <Database size={18} />
            <h3>证据来源</h3>
          </div>
          {evidence.length > 0 ? (
            <ul className="research-evidence-list">
              {evidence.map((ev) => (
                <li key={ev.id}>
                  <strong>{ev.source_title}</strong>
                  <p>{ev.snippet}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="research-empty">证据收集完成后，来源和摘要将显示在这里</p>
          )}
        </section>

        {/* QA issues */}
        {qaIssues.length > 0 && (
          <section className="research-section research-section--warning">
            <div className="research-section-title">
              <ShieldCheck size={18} />
              <h3>质量门反馈</h3>
            </div>
            <ul className="research-qa-list">
              {qaIssues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          </section>
        )}

        {/* Chat & Export row */}
        {phase === "done" && (
          <section className="research-actions">
            <div className="research-chat">
              <div className="research-section-title">
                <Search size={18} />
                <h3>项目问答</h3>
              </div>
              <div className="research-chat-row">
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
                <div className="research-chat-answer">
                  <p>{chat.answer}</p>
                  <span>引用：{chat.citations.join(", ")}</span>
                </div>
              )}
            </div>

            <div className="research-export">
              <button className="primary" onClick={exportProject}>
                <Download size={18} />
                导出知识库
              </button>
              {exportManifest && (
                <p className="research-export-result">
                  已导出 {exportManifest.artifact_paths.length} 个文件
                </p>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  App root                                                           */
/* ------------------------------------------------------------------ */

export function App() {
  const { toasts, removeToast, success, error } = useToast();

  const [phase, setPhase] = useState<AppPhase>("landing");
  const [project, setProject] = useState<Project | null>(null);
  const [currentGate, setCurrentGate] = useState("scope");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [qaIssues, setQaIssues] = useState<string[]>([]);
  const [statusText, setStatusText] = useState("等待启动");
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<ChatResponse | null>(null);
  const [exportManifest, setExportManifest] = useState<ExportManifest | null>(null);

  const [showConfig, setShowConfig] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  async function startResearch(domain: string) {
    setIsLoading(true);
    setQaIssues([]);
    setChat(null);
    setExportManifest(null);
    setPhase("running");
    setStatusText("运行中");

    try {
      const created = await requestJson<Project>("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          title: domain,
          domain,
          market_scope: "mixed",
          depth: "quick",
        }),
      });

      const state = await requestJson<ResearchState>(`/api/projects/${created.id}/runs`, {
        method: "POST",
      });

      const evItems = await requestJson<Evidence[]>(
        `/api/projects/${created.id}/evidence`,
      );

      setProject(created);
      setCurrentGate(state.current_gate);
      setArtifacts(state.artifacts);
      setEvidence(evItems);
      setQaIssues(state.qa_issues ?? []);
      setPhase("done");
      setStatusText((state.qa_issues ?? []).length > 0 ? "等待质量处理" : "运行完成");
      success("研究完成！");
    } catch (err) {
      const message = err instanceof Error ? err.message : "启动研究失败";
      error(message);
      setPhase("landing");
      setStatusText("启动失败");
    } finally {
      setIsLoading(false);
    }
  }

  async function askQuestion() {
    if (!project || !question.trim()) return;
    try {
      const response = await requestJson<ChatResponse>(`/api/projects/${project.id}/chat`, {
        method: "POST",
        body: JSON.stringify({ question }),
      });
      setChat(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : "问答请求失败";
      error(message);
    }
  }

  async function exportProject() {
    if (!project) return;
    try {
      const manifest = await requestJson<ExportManifest>(`/api/projects/${project.id}/exports`, {
        method: "POST",
      });
      setExportManifest(manifest);
      success("导出成功！");
    } catch (err) {
      const message = err instanceof Error ? err.message : "导出失败";
      error(message);
    }
  }

  function resetToLanding() {
    setPhase("landing");
    setProject(null);
    setCurrentGate("scope");
    setArtifacts([]);
    setEvidence([]);
    setQaIssues([]);
    setStatusText("等待启动");
    setQuestion("");
    setChat(null);
    setExportManifest(null);
  }

  return (
    <main className="shell">
      <ToastContainer toasts={toasts} onRemove={removeToast} />
      <ConfigPanel
        isOpen={showConfig}
        onClose={() => setShowConfig(false)}
        onSuccess={success}
        onError={error}
      />

      {phase === "landing" || !project ? (
        <LandingPage
          onStart={startResearch}
          onOpenSettings={() => setShowConfig(true)}
          isLoading={isLoading}
        />
      ) : (
        <ResearchView
          project={project}
          currentGate={currentGate}
          phase={phase}
          artifacts={artifacts}
          evidence={evidence}
          qaIssues={qaIssues}
          statusText={statusText}
          question={question}
          setQuestion={setQuestion}
          chat={chat}
          askQuestion={askQuestion}
          exportManifest={exportManifest}
          exportProject={exportProject}
          onNewResearch={resetToLanding}
        />
      )}
    </main>
  );
}
