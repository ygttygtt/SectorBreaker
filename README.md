# SectorBreaker 领域破壁

SectorBreaker 是一个基于 LangGraph 和多 Agent 协作的本地行业研究工作台。

它要解决的问题很直接：当你进入一个陌生领域时，不再只是到处搜索、收藏链接、问 AI 一句“这个行业怎么样”，然后得到一篇很快就忘掉的报告；而是让 Agent 帮你把碎片信息整理成一套可持续沉淀、可追溯证据、可导入 Obsidian 的领域认知系统。

换句话说，SectorBreaker 想做的不是“生成一篇行业分析报告”，而是帮你快速打破信息差，知道：

- 这个领域应该先学什么；
- 行业边界和常见误区是什么；
- 当前市场现状大概如何；
- 谁是玩家，谁掌握用户、渠道、资源和交付；
- 用户真正付钱购买的交易单位是什么；
- 内容、渠道、关键词和信任资产如何影响转化；
- 哪里可能存在需求、机会和风险；
- 哪些结论有证据，哪些只是待验证假设。

## 项目定位

SectorBreaker 首版定位为 **本地个人研究工作台**。

它不是团队 SaaS，也不是一次性 Prompt 工具。首版重点是把研究流程、Agent 分工、证据结构、知识库导出和项目问答打通，后续再逐步升级到 RAG、持续监控、周报、多人协作和云端部署。

## 核心思路

项目方法论来自“领域破壁”的研究流程：

1. **建数据库**：先建立行业市场、玩家、交易单位等结构化数据。
2. **反向拆解**：拆竞品商业结构、收入模型、转化路径和信任资产。
3. **内容生态**：研究平台内容、关键词、账号、选题和用户决策焦虑。
4. **知识地图**：把领域拆成可学习、可链接、可沉淀的知识卡片。
5. **情报系统**：后续升级为持续监控、周报和机会追踪。

首版不会直接实现完整第五步的订阅监控。它会先聚焦在“我想了解一个领域，用这个 Agent 就能比搜索和普通 AI 问答更系统地建立认知”。

## 当前已完成

目前项目已经完成工程地基和本地 MVP 闭环：

- 文档优先的协作规范：`AGENTS.md`、`CLAUDE.md`、`docs/`、`.claude/memory/`。
- Pydantic schema：项目、证据、产物、LangGraph state。
- Provider 抽象与环境装配：LLM、搜索、检索、导出。
- OpenAI 兼容 `LLMProvider`：通过 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 启用。
- Tavily 搜索 provider：已用 fake HTTP 测试，不依赖真实 API。
- SQLite 存储：项目、证据、产物、FTS 检索。
- LangGraph 研究 workflow：范围、证据、研究框架、知识地图、机会地图、QA 质量门、导出关口。
- Markdown / Obsidian 导出器。
- FastAPI API：项目创建/列表/详情、运行、证据、产物、导出、项目问答。
- Vite + React + TypeScript 前端“破壁工作台”已接入 API。
- Vite 开发代理已配置 `/api -> http://127.0.0.1:8030`。

## 技术栈

- Python 3.11+
- LangGraph
- FastAPI
- Pydantic v2
- SQLite + FTS
- Vite + React + TypeScript
- Obsidian-friendly Markdown export

## 快速开始

### 环境准备

```bash
conda env create -f environment.yml   # 首次安装
conda activate sectorbreaker           # 激活环境
cd frontend && npm install             # 首次安装前端依赖
```

### 启动项目

需要两个终端窗口，先激活 conda 环境再启动服务，`Ctrl+C` 随时停掉对应服务。

**终端 1 — 后端**（端口 8030）：

```bash
conda activate sectorbreaker
python -m uvicorn backend.app.api.app:app --port 8030 --reload
```

**终端 2 — 前端**（端口 5173）：

```bash
conda activate sectorbreaker
cd frontend
npm run dev
```

打开浏览器访问 `http://127.0.0.1:5173/`。

### 测试

```bash
# 后端测试
conda activate sectorbreaker
python -m pytest -q

# 前端测试和构建
cd frontend
npm test
npm run build
```

## 后续最重要的工作

下一阶段不是继续堆页面，而是增强研究质量和协作能力：

1. 把 Research Planner 输出从 raw `dict` 升级为专用 Pydantic schema。
2. 增强 Evidence Curator，细分来源质量、冲突证据和验证状态。
3. 为 Tavily Search Scout 增加多查询规划和空结果诊断。
4. 加入 LangGraph interrupt/resume，支持阶段性人工确认。
5. 增加 artifact 全文检索和更好的项目问答答案生成。
6. 做两个验收案例，沉淀 golden export fixture。
7. v2 再做 embeddings/RAG、持续监控、周报和多人账号协作。

详细交接说明见：

- `docs/10-current-status-and-handoff.md`
- `.claude/memory/current-progress-and-handoff.md`

## 协作规则

这是一个多人、多 Agent 接力开发项目。任何贡献者或 Agent 在动手前都应该先读：

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/10-current-status-and-handoff.md`
4. `docs/11-tooling-handoff.md`
5. 与自己任务相关的 `docs/0x-*.md`

核心原则：

- 文档先行。
- schema 先行。
- 测试先行。
- 证据先行。
- Agent 输出必须结构化。
- 外部能力必须通过 provider 接口。
- 关键研究结论必须关联 evidence id。

以后提交日志统一使用中文。
