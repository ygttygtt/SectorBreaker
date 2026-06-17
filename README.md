# SectorBreaker

**用 AI 多智能体协同，1 小时内建立可持续更新的行业认知系统。**

> 📖 完整设计理念、方法论和 Prompt 参考：[SectorBreaker 领域破壁设计稿](SectorBreaker领域破壁设计稿.md)

## 为什么做这个

大部分人进入陌生领域时，习惯去问 AI、刷报告、收藏链接。几天后脑子里还是乱的——得到的是**信息**，不是**系统**。

SectorBreaker 不是给你写一篇行业报告，而是帮你搭建一个**可以继续填充、继续更新、继续判断的行业认知系统**。

## Features

- **可解释主管计划** — Supervisor 先生成作战计划，说明启用/跳过哪些 Agent 以及原因
- **信源策略可选** — 支持开放网络、可靠优先、严格可靠、仅用户材料四种模式
- **外部 AI 报告借力** — 可手动粘贴 Gemini/Kimi/Qwen/DeepSeek 报告，但只作为低可信线索
- **证据账本与反证** — Evidence Ledger 记录来源质量、claim、偏见风险和反证标记
- **实时运行图** — 前端展示真实 workflow、节点状态、加载进度和 SSE 事件流
- **Obsidian 导出** — 一键生成 Markdown 知识库，直接导入 Obsidian

## Quick Start

```bash
# 1. 安装依赖
conda activate sectorbreaker
pip install -e "backend[dev]"
cd frontend && npm install && cd ..

# 2. 配置 LLM（启动后在页面右下角设置）
# 支持任何 OpenAI 兼容 API（DeepSeek、OpenRouter、本地 Ollama 等）

# 3. 启动后端
python -m uvicorn backend.app.api.app:app --port 8030 --reload

# 4. 启动前端（新终端）
cd frontend && npm run dev

# 5. 打开 http://127.0.0.1:5173/
```

## Architecture

```
用户输入领域 + 信源模式
    ↓
┌─────────────────────────────────────────────┐
│  LangGraph Explainable Research Workflow     │
│                                              │
│  [范围确认] → [主管计划] → [人工确认]         │
│       ↓           ↓           ↓              │
│   研究边界    Agent 选择    用户补方向/材料   │
│                                              │
│  → [信源策略] → [证据账本] → [商业分析]       │
│       ↓             ↓             ↓          │
│   搜索/材料/报告  来源评级/反证   市场/玩家/交易│
│                                              │
│  → [QA 质量门] → [导出] → [RAG 索引]          │
└─────────────────────────────────────────────┘
    ↓
Obsidian 知识库 + SQLite 结构化存储
```

核心设计：**固定大阶段 + 阶段内动态 Agent + 证据优先质量门**。系统不是把长 Prompt 串起来，而是用 LangGraph 管理状态、分支、并行、人工确认、QA 阻塞和实时进度。

## Agent Pool

| Agent | 职责 |
|-------|------|
| Supervisor Agent | 研究意图归纳、Agent 选择、作战计划 |
| Source Strategy Agent | 信源模式与来源范围 |
| Research Planner | 研究框架与学习路径 |
| Search Scout | 外部搜索 |
| Assistant Brief Agent | 外部 AI 报告 claim 拆解，低可信线索 |
| Evidence Curator | 证据规范化、来源评级、claim 标注 |
| Counterevidence Agent | 关键低可信结论反证标记 |
| Market Mapper | 市场规模、增长、约束 |
| Player Analyst | 玩家角色、议价能力、商业模式 |
| Transaction Analyst | 交易单位、定价、频率、风险 |
| Content Channel Analyst | 内容生态、渠道、转化路径 |
| Knowledge Mapper | 知识地图与卡片 |
| Opportunity Analyst | 机会假设与验证路径 |
| QA Critic | 质量门禁、证据链检查 |
| Export Writer | Markdown/Obsidian 导出 |
| RAG Indexer | 本地 FTS/RAG 接口预留 |

## Tech Stack

- **LangGraph** — 多智能体编排
- **Python + FastAPI** — 后端 API
- **Vite + React + TypeScript** — 前端工作台
- **SQLite** — 本地存储与 FTS 检索
- **Obsidian** — 知识库输出格式

## Project Structure

```
backend/
  app/
    api/          # FastAPI endpoints
    graph/        # LangGraph workflow
    providers/    # LLM / Search provider interfaces
    schemas/      # Pydantic models
    storage/      # SQLite repository
    exporters/    # Markdown / Obsidian export
frontend/
  src/
    api/          # API client
    components/   # React components (GraphFlow, ReviewView, etc.)
    hooks/        # useRunEvents (SSE)
docs/             # Architecture & contracts
```

## Documentation

- [设计稿](SectorBreaker领域破壁设计稿.md) — 完整方法论与 Prompt
- [架构设计](docs/01-architecture.md) — 系统架构与 Gate 设计
- [Agent 合约](docs/02-agent-contracts.md) — 每个 Agent 的输入输出规范
- [快速上手](docs/quickstart.md) — 详细启动与配置指南

## License

Private / Internal Use
