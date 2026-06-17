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

- conda 环境：`sectorbreaker`
- 后端：FastAPI + LangGraph + SQLite + provider factory + Supervisor Plan + Evidence Ledger
- 前端：Vite + React + TypeScript，可解释研究工作台，真实 workflow graph
- 测试基线：Python 23 passed；前端 3 passed；前端 build passed

最高风险任务：

- 剩余业务 Agent Pydantic 输出 schema 和 prompt
- 可靠信源包、真实 Counterevidence 搜索、Evidence Curator 可信度/冲突规则
- QA Critic artifact prose unsupported-claim 检测
- LangGraph interrupt/resume/checkpoint
- public schema / graph state / export format / provider interface 变更

适合分发任务：

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
