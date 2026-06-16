# SectorBreaker

**用 AI 多智能体协同，1 小时内建立可持续更新的行业认知系统。**

> 📖 完整设计理念、方法论和 Prompt 参考：[SectorBreaker 领域破壁设计稿](SectorBreaker领域破壁设计稿.md)

## 为什么做这个

大部分人进入陌生领域时，习惯去问 AI、刷报告、收藏链接。几天后脑子里还是乱的——得到的是**信息**，不是**系统**。

SectorBreaker 不是给你写一篇行业报告，而是帮你搭建一个**可以继续填充、继续更新、继续判断的行业认知系统**。

## Features

- **结构化行业研究** — 从范围确认到知识地图，6 个 Gate 逐步深入
- **多智能体协同** — 11 个专业 Agent 各司其职（规划、搜索、证据、分析、质检、导出）
- **人工审阅机制** — 关键节点暂停等待确认，支持注入已有信息补充 AI 研究
- **实时进度流** — SSE 推送研究事件，全程可视化
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
用户输入领域
    ↓
┌─────────────────────────────────────────────┐
│  LangGraph Adaptive Research Workflow        │
│                                              │
│  [范围确认] → [证据收集] → [研究框架]         │
│       ↓           ↓           ↓              │
│  人工审阅     搜索引擎      LLM 规划          │
│                                              │
│  → [知识地图] → [机会地图] → [质量门] → [导出] │
│       ↓           ↓                        │
│   行业/玩家     机会假设                     │
└─────────────────────────────────────────────┘
    ↓
Obsidian 知识库 + SQLite 结构化存储
```

核心设计：**固定质量门 + 动态 Supervisor 任务分配**。Gate 外壳保证研究质量，内部 Agent 灵活应对不同行业。

## Agent Pool

| Agent | 职责 |
|-------|------|
| Research Planner | 研究框架与学习路径 |
| Search Scout | 外部搜索 |
| Evidence Curator | 证据规范化与置信度标注 |
| Market Mapper | 市场规模、增长、约束 |
| Player Analyst | 玩家角色、议价能力、商业模式 |
| Transaction Analyst | 交易单位、定价、频率、风险 |
| Content Channel Analyst | 内容生态、渠道、转化路径 |
| Knowledge Mapper | 知识地图与卡片 |
| Opportunity Analyst | 机会假设与验证路径 |
| QA Critic | 质量门禁、证据链检查 |
| Export Writer | Markdown/Obsidian 导出 |

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
