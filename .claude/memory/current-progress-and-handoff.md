---
name: current-progress-and-handoff
description: SectorBreaker 当前进度、剩余任务、可分发任务、强把控任务和项目记忆同步方式
metadata:
  type: project
---

接手 SectorBreaker 前必须先读：

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/10-current-status-and-handoff.md`
4. 与任务相关的 `docs/0x-*.md`

当前状态：

- 文档与协作规范已建立。
- 核心 schema、provider interfaces、provider factory、SQLite migration/repository 已建立。
- OpenAI 兼容 LLM provider 已实现，可通过 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 启用。
- Tavily search provider 可通过 `TAVILY_API_KEY` 启用。
- LangGraph workflow 已跑通 provider 注入、证据整理、研究框架、知识地图、机会地图、QA 质量门和导出关口。
- Markdown/Obsidian 导出器已跑通。
- FastAPI API 已跑通项目 create/list/detail、run、evidence、artifacts、export、chat。
- React/Vite 破壁工作台已接入 API：启动研究、展示证据/产物、项目问答、导出。
- Vite 已代理 `/api` 到 `http://127.0.0.1:8000`。

强把控任务：

- Research Planner 专用 Pydantic 输出 schema。
- Tavily Search Scout 多查询规划与 Evidence Curator 可信度规则。
- QA Critic unsupported-claim 检测与 retry 建议。
- LangGraph interrupt/resume 与 checkpoint 策略。
- Agent contract/schema 变更。

适合分发任务：

- 前端可编辑项目表单与 API client 抽取。
- artifact detail viewer 与 evidence filters。
- 产物页面细化。
- Markdown 导出样式。
- 示例 fixture。
- 文档补充和验收样例。

验证基线：

- `python -m pytest -q`：21 passed，1 个 FastAPI TestClient/Starlette deprecation warning。
- `cd frontend && npm test -- --run`：4 passed。
- `cd frontend && npm run build`：通过。

记忆同步：

- 状态变化更新 `docs/10-current-status-and-handoff.md`。
- 跨工具接手信息变化更新 `docs/11-tooling-handoff.md`。
- Claude Code 记忆变化更新 `.claude/memory/MEMORY.md` 和对应 memory 文件。
- 跨工具接手记忆变化更新 `.claude/memory/tooling-handoff.md`。
- 协作规则变化更新 `AGENTS.md`。
- Claude 入口说明变化更新 `CLAUDE.md`。
- 提交后同时推送 `origin main` 和 `gitee main`。
