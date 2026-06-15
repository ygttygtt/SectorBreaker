---
name: tooling-handoff
description: SectorBreaker 跨工具接手入口，适用于 Cursor、Windsurf、Gemini、Claude Code、Codex 等后续开发工具
metadata:
  type: project
---

后续任何工具或 Agent 接手时，不要依赖原始聊天记录。以仓库文档为准。

必读顺序：

1. `AGENTS.md`
2. `README.md`
3. `docs/10-current-status-and-handoff.md`
4. `docs/11-tooling-handoff.md`
5. 当前任务相关的 `docs/0x-*.md`

当前基线：

- 最近完成提交：`8384628 实现本地研究闭环与前端联通`
- conda 环境：`sectorbreaker`
- 后端：FastAPI + LangGraph + SQLite + provider factory
- 前端：Vite + React + TypeScript，工作台名为“破壁工作台”
- 测试基线：Python 21 passed；前端 4 passed；前端 build passed；npm audit high 0

最高风险任务：

- Research Planner Pydantic 输出 schema 和 prompt
- Evidence Curator 可信度/冲突规则
- QA Critic unsupported-claim 检测
- LangGraph interrupt/resume/checkpoint
- public schema / graph state / export format / provider interface 变更

适合分发任务：

- 前端可编辑项目表单
- typed API client 抽取
- artifact detail viewer
- evidence filters
- export 样式优化
- deterministic fixtures / golden export tests

记忆同步时同时更新：

- `docs/10-current-status-and-handoff.md`
- `docs/11-tooling-handoff.md`
- `.claude/memory/current-progress-and-handoff.md`
- `.claude/memory/tooling-handoff.md`
- 必要时更新 `README.md`、`AGENTS.md`、`CLAUDE.md`
