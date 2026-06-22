# SectorBreaker

**用 AI 多智能体协同，1 小时内建立可持续更新的行业认知系统。**

> 📖 完整设计理念、方法论和 Prompt 参考：[SectorBreaker 领域破壁设计稿](SectorBreaker领域破壁设计稿.md)

## 为什么做这个

大部分人进入陌生领域时，习惯去问 AI、刷报告、收藏链接。几天后脑子里还是乱的——得到的是**信息**，不是**系统**。

SectorBreaker 不是给你写一篇行业报告，而是帮你搭建一个**可以继续填充、继续更新、继续判断的行业认知系统**。

## Features

- **可解释主管计划** — Supervisor 先生成作战计划，说明启用/跳过哪些 Agent 以及原因
- **信源策略可选** — 支持开放网络、可靠优先、严格可靠、仅用户材料四种模式
- **搜索能力显式可见** — 未配置网络搜索时，前端会明确提醒，不会静默假装具备联网能力
- **外部 AI 报告借力** — 可手动粘贴 Gemini/Kimi/Qwen/DeepSeek 报告，但只作为低可信线索
- **多搜索底座已就绪** — 当前可通过 Tavily / Serper / Brave / Exa 启用单一或聚合搜索 provider
- **报告上传入口已就绪** — 当前前后端都支持 `.md` / `.txt` 文本文件上传，外部 AI 报告和用户材料会先入库，再进入后续引用验证与交叉验证流程
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

## Search Setup

复制一份配置模板：

```bash
cp .env.example .env
```

后端启动和 CLI smoke test 都会自动读取项目根目录下的 `.env`。
你也可以直接在前端 `LLM 设置` 面板里保存搜索/抽取配置并立即测试，不必改 `.env`。

可选设置搜索模式：

```bash
SEARCH_PROVIDER_MODE=auto
```

可用值：

- `auto`：默认行为，单 key 走单 provider，多 key 自动聚合
- `multi`：强制聚合当前可用 provider
- `tavily` / `serper` / `brave` / `exa`：强制单一 provider

至少配置一组搜索 provider：

```bash
TAVILY_API_KEY=...
# 或
SERPER_API_KEY=...
# 或
BRAVE_API_KEY=...
# 或
EXA_API_KEY=...
```

可选配置正文抽取 provider：

```bash
CONTENT_EXTRACTION_PROVIDER=firecrawl
FIRECRAWL_API_KEY=...

# 或
CONTENT_EXTRACTION_PROVIDER=jina
```

如果不配置抽取 provider，系统会默认使用本地 `http` fallback。

## Search Connectivity Check

配完 key 后，推荐先验证搜索/抽取链是否可用：

```bash
curl -X POST http://127.0.0.1:8030/api/config/search/test ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"AI agent market map\",\"market_scope\":\"mixed\",\"max_results\":3}"
```

返回会包含：

- 当前启用的搜索 provider 名称
- 当前实际生效的 `source_policy`
- 当前实际生效的 allowed / blocked domains
- 搜索结果数量和样例结果
- 默认会自动抽取首条搜索结果，并返回页面预览与来源评估
- 如果你想指定抽取目标，也可以额外传 `url_to_extract`
- 也支持额外传 `allowed_domains` / `blocked_domains` 做域名白名单或黑名单验证

也可以直接在前端右下角打开 `LLM 设置` 面板，使用其中的 `测试搜索链路` 按钮完成同样的验证，无需手动调用 curl。
该面板现在也支持直接选择 `open_web / reliable_first / reliable_only / user_materials_only`，用来模拟真实 workflow 的搜索策略。

当前 landing 页也会直接显示正在启用的搜索 provider 和正文抽取 provider，方便确认你配置的真实 API 是否已经生效。

## CLI Smoke Test

如果你想在命令行一次性验证“搜索 -> 抽取 -> 来源评估”整条链，可以直接运行：

```bash
python run_search_smoke_test.py
```

它会读取 `.env`，调用当前配置的 search provider 和 extraction provider，并打印 JSON 结果摘要。

如果你想验证域名约束是否生效，也可以额外设置：

```bash
SECTORBREAKER_SMOKE_SOURCE_POLICY=reliable_only
SECTORBREAKER_SMOKE_ALLOWED_DOMAINS=sec.gov,investor.example.com
SECTORBREAKER_SMOKE_BLOCKED_DOMAINS=medium.com,substack.com
```

## Real Acceptance Script

如果你已经填好了真实 provider key，想一次性验证“搜索配置 -> 搜索自检 -> 项目 run -> evidence 入库”整条链，可以直接运行：

```bash
python run_real_search_acceptance.py
```

它会自动：

- 调用 `/api/config/search` 检查当前 provider 是否已启用
- 调用 `/api/config/search/test` 跑一次真实搜索
- 自动创建项目并触发 `auto_run=true`
- 最后检查项目 evidence 列表里是否真的写入了 `source_channel=search` 的搜索证据

可选环境变量：

```bash
SECTORBREAKER_API_BASE_URL=http://127.0.0.1:8000
SECTORBREAKER_ACCEPTANCE_QUERY=AI agent market map
SECTORBREAKER_ACCEPTANCE_SOURCE_POLICY=open_web
SECTORBREAKER_ACCEPTANCE_ALLOWED_DOMAINS=sec.gov,stats.gov.cn
SECTORBREAKER_ACCEPTANCE_BLOCKED_DOMAINS=medium.com
```

## Minimal Env Template

如果你想先快速生成一个“最小可用”的 `.env` 片段，而不是手工从 `.env.example` 里裁剪，可以直接运行：

```bash
python generate_search_env_template.py tavily http
```

如果你想直接写出 `.env` 文件：

```bash
python generate_search_env_template.py tavily http --write .env
```

或：

```bash
python generate_search_env_template.py brave jina
```

第一个参数是搜索 provider，可选：

- `tavily`
- `serper`
- `brave`
- `exa`

第二个参数是抽取 provider，可选：

- `http`
- `firecrawl`
- `jina`

如果你不传参数，默认会输出：

```bash
python generate_search_env_template.py
```

也就是推荐的最简起步组合：`tavily + http`。

## Real API Onboarding Checklist

推荐按这个顺序完成真实搜索 provider 接入验收：

1. 复制 `[.env.example](.env.example)` 为 `.env`，至少填 `TAVILY_API_KEY`、`SERPER_API_KEY`、`BRAVE_API_KEY`、`EXA_API_KEY` 四者之一。
2. 如果要用 Firecrawl，额外填 `FIRECRAWL_API_KEY` 并设置 `CONTENT_EXTRACTION_PROVIDER=firecrawl`。
3. 启动后端后先看 landing 页是否显示真实 `搜索 Provider` / `抽取 Provider`。
4. 打开 `LLM 设置` 面板，确认搜索状态卡片没有缺失配置提示。
5. 点击 `测试搜索链路`，确认能返回结果数、首条结果、抽取页面预览、来源评估。
6. 再运行 `python run_search_smoke_test.py`，确认 CLI 输出里有：
   `result_count > 0`
   `first_result_source_quality`
   `first_result_verification_status`
7. 再运行 `python run_real_search_acceptance.py`，把真实搜索、项目运行、evidence 入库串成一次完整验收。
8. 如果你仍想手动复核，再单独新建一个研究项目，跑一次 `auto_run=true`，确认开放搜索证据会进入 evidence 列表。

如果验收失败，优先看三处：

- `/api/config/search` 返回的 `missing_configuration`
- `/api/config/search` 返回的 `diagnostics`
- `run_search_smoke_test.py` 的 stderr / stdout 摘要

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
- [搜索与报告接入设计](docs/14-search-and-report-ingestion-design.md) — 多 provider 搜索、文件上传、引用来源验证、交叉验证扩展设计
- [真实搜索接入验收](docs/15-real-search-provider-onboarding.md) — 从填 key 到 API / CLI / 项目 run 验收成功的落地清单
- [快速上手](docs/quickstart.md) — 详细启动与配置指南

## License

Private / Internal Use
