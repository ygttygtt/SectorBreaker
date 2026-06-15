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
- 核心 schema、provider interfaces、SQLite migration/repository 已建立。
- LangGraph 最小 deterministic workflow 已跑通。
- Markdown/Obsidian 导出器已跑通。
- FastAPI 最小 API 已跑通。
- React/Vite 破壁工作台壳子已跑通。

强把控任务：

- 真实 LLM Planner structured output。
- Tavily Search Scout 与 Evidence Curator。
- QA Critic 证据门禁。
- LangGraph interrupt/resume 与 checkpoint 策略。
- Agent contract/schema 变更。

适合分发任务：

- 前端表单与 API client。
- 产物页面细化。
- Markdown 导出样式。
- 示例 fixture。
- 文档补充和验收样例。

记忆同步：

- 状态变化更新 `docs/10-current-status-and-handoff.md`。
- Claude Code 记忆变化更新 `.claude/memory/MEMORY.md` 和对应 memory 文件。
- 协作规则变化更新 `AGENTS.md`。
- Claude 入口说明变化更新 `CLAUDE.md`。
- 提交后同时推送 `origin main` 和 `gitee main`。
