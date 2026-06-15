import { useState } from "react";
import {
  ArrowRight,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ClipboardCheck,
  Database,
  Download,
  FileText,
  Layers3,
  Play,
  Search,
  ShieldCheck
} from "lucide-react";

import "./styles.css";

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

const gateLabels = [
  { key: "scope", name: "范围确认" },
  { key: "research_frame", name: "研究框架" },
  { key: "evidence", name: "资料证据" },
  { key: "knowledge_map", name: "知识地图" },
  { key: "opportunity", name: "机会地图" },
  { key: "export", name: "知识库导出" }
];

const projectTemplate = {
  title: "AI Agent Tools",
  domain: "AI Agent 工具",
  market_scope: "mixed",
  depth: "quick"
};

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init
  });
  if (!response.ok) {
    throw new Error(`API 请求失败: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function gateStatus(gateKey: string, currentGate: string) {
  const currentIndex = gateLabels.findIndex((gate) => gate.key === currentGate);
  const gateIndex = gateLabels.findIndex((gate) => gate.key === gateKey);
  if (currentIndex === -1 || gateIndex < currentIndex) return "done";
  if (gateIndex === currentIndex) return "current";
  return "next";
}

export function App() {
  const [project, setProject] = useState<Project | null>(null);
  const [currentGate, setCurrentGate] = useState("scope");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [qaIssues, setQaIssues] = useState<string[]>([]);
  const [statusText, setStatusText] = useState("等待启动");
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<ChatResponse | null>(null);
  const [exportManifest, setExportManifest] = useState<ExportManifest | null>(null);

  async function startResearch() {
    setStatusText("运行中");
    setQaIssues([]);
    setChat(null);
    setExportManifest(null);
    const createdProject = await requestJson<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify(projectTemplate)
    });
    const state = await requestJson<ResearchState>(`/api/projects/${createdProject.id}/runs`, {
      method: "POST"
    });
    const evidenceItems = await requestJson<Evidence[]>(
      `/api/projects/${createdProject.id}/evidence`
    );

    setProject(createdProject);
    setCurrentGate(state.current_gate);
    setArtifacts(state.artifacts);
    setEvidence(evidenceItems);
    setQaIssues(state.qa_issues ?? []);
    setStatusText((state.qa_issues ?? []).length > 0 ? "等待质量处理" : "运行完成");
  }

  async function askQuestion() {
    if (!project || !question.trim()) return;
    const response = await requestJson<ChatResponse>(`/api/projects/${project.id}/chat`, {
      method: "POST",
      body: JSON.stringify({ question })
    });
    setChat(response);
  }

  async function exportProject() {
    if (!project) return;
    const manifest = await requestJson<ExportManifest>(`/api/projects/${project.id}/exports`, {
      method: "POST"
    });
    setExportManifest(manifest);
  }

  return (
    <main className="shell">
      <aside className="sidebar" aria-label="项目导航">
        <div className="brand">
          <Bot size={24} />
          <div>
            <h1>SectorBreaker</h1>
            <span>领域破壁系统</span>
          </div>
        </div>
        <div className="run-badge">
          <ShieldCheck size={16} />
          本地安全闭环
        </div>
        <nav>
          <a className="active" href="#workspace">
            破壁工作台
          </a>
          <a href="#gates">阶段关口</a>
          <a href="#evidence">证据与产物</a>
          <a href="#qa">质量门</a>
        </nav>
      </aside>

      <section className="workspace" id="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">本地个人研究工作台</p>
            <h2>破壁工作台</h2>
          </div>
          <div className="actions">
            <button className="primary" type="button" onClick={startResearch}>
              <Play size={18} />
              启动研究
            </button>
            <button
              className="secondary"
              type="button"
              onClick={exportProject}
              disabled={!project}
            >
              <Download size={18} />
              导出知识库
            </button>
          </div>
        </header>

        <section className="project-strip" aria-label="当前项目">
          <div>
            <span className="label">领域</span>
            <strong>{project?.domain ?? projectTemplate.domain}</strong>
          </div>
          <div>
            <span className="label">市场范围</span>
            <strong>{project?.market_scope ?? projectTemplate.market_scope}</strong>
          </div>
          <div>
            <span className="label">运行状态</span>
            <strong>{statusText}</strong>
          </div>
          <div>
            <span className="label">当前关口</span>
            <strong>{currentGate}</strong>
          </div>
        </section>

        <div className="grid">
          <section className="panel" id="gates">
            <div className="panel-title">
              <ClipboardCheck size={18} />
              <h3>阶段关口</h3>
            </div>
            <ol className="gates">
              {gateLabels.map((gate, index) => (
                <li className={gateStatus(gate.key, currentGate)} key={gate.key}>
                  <span>{index + 1}</span>
                  <strong>{gate.name}</strong>
                </li>
              ))}
            </ol>
          </section>

          <section className="panel" id="evidence">
            <div className="panel-title">
              <Database size={18} />
              <h3>证据与产物</h3>
            </div>
            <ul className="artifacts">
              {(artifacts.length > 0 ? artifacts : defaultArtifacts()).map((artifact) => (
                <li key={artifact.id}>
                  <FileText size={16} />
                  <span>{artifact.id}</span>
                  <em>{artifact.content_path}</em>
                </li>
              ))}
            </ul>
          </section>

          <section className="panel">
            <div className="panel-title">
              <BrainCircuit size={18} />
              <h3>Agent 状态</h3>
            </div>
            <div className="status-list">
              <p>
                <CheckCircle2 size={16} />
                Schema / Provider / SQLite 已接入
              </p>
              <p>
                <Layers3 size={16} />
                LangGraph 固定关口已启用
              </p>
              <p>
                <ArrowRight size={16} />
                下一步：接入真实 LLM 与检索任务
              </p>
            </div>
          </section>

          <section className="panel" id="qa">
            <div className="panel-title">
              <ShieldCheck size={18} />
              <h3>质量门</h3>
            </div>
            <div className="roadmap">
              {(qaIssues.length > 0 ? qaIssues : ["证据引用检查通过", "Coverage 检查通过"]).map(
                (item) => (
                  <span key={item}>{item}</span>
                )
              )}
            </div>
          </section>

          <section className="panel wide" id="export">
            <div className="panel-title">
              <Search size={18} />
              <h3>项目问答</h3>
            </div>
            <div className="query-row">
              <input
                aria-label="项目问题"
                placeholder="基于当前研究项目继续追问"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
              <button type="button" onClick={askQuestion} disabled={!project}>
                询问
              </button>
            </div>
            {chat ? (
              <div className="answer">
                <strong>{chat.answer}</strong>
                <span>引用：{chat.citations.join(", ")}</span>
              </div>
            ) : null}
            {exportManifest ? (
              <div className="answer">
                <strong>已导出 {exportManifest.artifact_paths.length} 个文件</strong>
                <span>证据：{exportManifest.evidence_ids.join(", ")}</span>
              </div>
            ) : null}
          </section>

          <section className="panel wide">
            <div className="panel-title">
              <Database size={18} />
              <h3>证据摘录</h3>
            </div>
            <ul className="evidence-list">
              {(evidence.length > 0 ? evidence : defaultEvidence()).map((item) => (
                <li key={item.id}>
                  <strong>{item.id}</strong>
                  <span>{item.source_title}</span>
                  <p>{item.snippet}</p>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </section>
    </main>
  );
}

function defaultArtifacts(): Artifact[] {
  return [
    {
      id: "ART-RESEARCH-FRAME",
      title: "研究框架",
      content_path: "00-研究框架/research-frame.md"
    },
    {
      id: "ART-INDUSTRY-MAP",
      title: "行业地图",
      content_path: "01-行业地图/industry-map.md"
    }
  ];
}

function defaultEvidence(): Evidence[] {
  return [
    {
      id: "EV-USER-SCOPE",
      source_title: "用户输入范围",
      snippet: "启动研究后，这里会展示证据来源、摘要和引用状态。"
    }
  ];
}
