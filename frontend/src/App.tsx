import {
  ArrowRight,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileText,
  Layers3,
  Play,
  Search,
  ShieldCheck
} from "lucide-react";

import "./styles.css";

const gates = [
  { name: "范围确认", status: "done" },
  { name: "研究框架", status: "done" },
  { name: "资料证据", status: "current" },
  { name: "知识地图", status: "next" },
  { name: "机会地图", status: "next" },
  { name: "知识库导出", status: "next" }
];

const artifacts = [
  { path: "00-研究框架/research-frame.md", tag: "已生成" },
  { path: "01-行业地图/industry-map.md", tag: "已生成" },
  { path: "05-机会地图/opportunity-map.md", tag: "待增强" }
];

export function App() {
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
          MVP 闭环已就绪
        </div>
        <nav>
          <a className="active" href="#cockpit">
            破壁工作台
          </a>
          <a href="#gates">阶段关口</a>
          <a href="#evidence">证据与产物</a>
          <a href="#next">升级路线</a>
        </nav>
      </aside>

      <section className="workspace" id="cockpit">
        <header className="topbar">
          <div>
            <p className="eyebrow">本地个人研究工作台</p>
            <h2>破壁工作台</h2>
          </div>
          <button className="primary" type="button">
            <Play size={18} />
            启动研究
          </button>
        </header>

        <section className="project-strip" aria-label="当前项目">
          <div>
            <span className="label">领域</span>
            <strong>AI Agent 工具</strong>
          </div>
          <div>
            <span className="label">市场范围</span>
            <strong>混合</strong>
          </div>
          <div>
            <span className="label">运行状态</span>
            <strong>最小闭环</strong>
          </div>
          <div>
            <span className="label">下一步</span>
            <strong>接入真实 LLM 与检索任务</strong>
          </div>
        </section>

        <div className="grid">
          <section className="panel" id="gates">
            <div className="panel-title">
              <ClipboardCheck size={18} />
              <h3>阶段关口</h3>
            </div>
            <ol className="gates">
              {gates.map((gate, index) => (
                <li className={gate.status} key={gate.name}>
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
              {artifacts.map((artifact) => (
                <li key={artifact.path}>
                  <FileText size={16} />
                  <span>{artifact.path}</span>
                  <em>{artifact.tag}</em>
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
                Schema / Provider / SQLite 已通过测试
              </p>
              <p>
                <Layers3 size={16} />
                LangGraph 已跑通 deterministic workflow
              </p>
              <p>
                <ArrowRight size={16} />
                下一步：接入真实 LLM 与检索任务
              </p>
            </div>
          </section>

          <section className="panel" id="next">
            <div className="panel-title">
              <ShieldCheck size={18} />
              <h3>升级路线</h3>
            </div>
            <div className="roadmap">
              <span>LLM Planner</span>
              <span>Tavily Evidence</span>
              <span>QA Critic</span>
              <span>FTS 问答增强</span>
            </div>
          </section>

          <section className="panel wide" id="export">
            <div className="panel-title">
              <Search size={18} />
              <h3>项目问答</h3>
            </div>
            <div className="query-row">
              <input aria-label="项目问题" placeholder="基于当前研究项目继续追问" />
              <button type="button">询问</button>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
