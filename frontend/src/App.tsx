import { Bot, CheckCircle2, Database, FileText, Play, Search } from "lucide-react";

import "./styles.css";

const gates = ["范围确认", "研究框架", "资料证据", "知识地图", "机会地图", "导出"];

const artifacts = [
  "00-研究框架/research-frame.md",
  "01-行业地图/industry-map.md",
  "05-机会地图/opportunity-map.md"
];

export function App() {
  return (
    <main className="shell">
      <aside className="sidebar" aria-label="项目导航">
        <div className="brand">
          <Bot size={24} />
          <h1>SectorBreaker</h1>
        </div>
        <nav>
          <a className="active" href="#cockpit">
            研究驾驶舱
          </a>
          <a href="#evidence">证据与产物</a>
          <a href="#export">知识库导出</a>
        </nav>
      </aside>

      <section className="workspace" id="cockpit">
        <header className="topbar">
          <div>
            <p className="eyebrow">本地个人研究工作台</p>
            <h2>研究驾驶舱</h2>
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
            <span className="label">研究深度</span>
            <strong>快速</strong>
          </div>
        </section>

        <div className="grid">
          <section className="panel">
            <div className="panel-title">
              <CheckCircle2 size={18} />
              <h3>固定关口</h3>
            </div>
            <ol className="gates">
              {gates.map((gate, index) => (
                <li key={gate}>
                  <span>{index + 1}</span>
                  {gate}
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
                <li key={artifact}>
                  <FileText size={16} />
                  {artifact}
                </li>
              ))}
            </ul>
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
