# SectorBreaker 项目架构

## 目录结构

```
SectorBreaker/
├── backend/                    # Python 后端
│   ├── app/
│   │   ├── api/                # FastAPI 路由
│   │   │   └── app.py          # 所有 API 端点（项目/运行/证据/产物/导出/LLM配置）
│   │   ├── graph/              # LangGraph 工作流
│   │   │   └── workflow.py     # 7 个 Gate 实现 + 暂停/恢复引擎
│   │   ├── providers/          # 外部服务接口
│   │   │   ├── interfaces.py   # LLM/Search/Retrieval Protocol 定义
│   │   │   ├── openai_compatible.py  # OpenAI 兼容 LLM 客户端
│   │   │   ├── tavily.py       # Tavily 搜索客户端
│   │   │   ├── factory.py      # 从环境变量构建 provider
│   │   │   └── fakes.py        # 测试用 mock provider
│   │   ├── schemas/            # Pydantic 数据模型
│   │   │   ├── projects.py     # ResearchProject, MarketScope, ResearchDepth
│   │   │   ├── artifacts.py    # Artifact, ArtifactType（15 种产物类型）
│   │   │   ├── evidence.py     # EvidenceItem, VerificationStatus
│   │   │   ├── runs.py         # ResearchRun, RunEvent, RunStatus, UserInput
│   │   │   └── state.py        # ResearchState, ResearchGate
│   │   ├── storage/            # 数据持久化
│   │   │   ├── sqlite.py       # SQLiteRepository（项目/证据/产物/运行/事件）
│   │   │   └── migrations/     # 数据库迁移
│   │   │       ├── 001_initial.sql       # projects + evidence + evidence_fts
│   │   │       ├── 002_artifacts.sql     # artifacts 表
│   │   │       ├── 003_runs.sql          # runs + run_events + user_inputs 表
│   │   │       └── 004_workflow_state.sql # runs.workflow_state 列
│   │   └── exporters/          # 导出器
│   │       └── markdown.py     # Markdown/Obsidian 格式导出
│   └── __init__.py
│
├── frontend/                   # Vite + React + TypeScript 前端
│   ├── src/
│   │   ├── api/
│   │   │   └── client.ts       # 类型安全的 API 客户端
│   │   ├── components/
│   │   │   ├── Logo.tsx         # 知识网络 Logo（6 节点 + GSAP 动画）
│   │   │   ├── GraphFlow.tsx    # 6 Gate 流程图可视化
│   │   │   ├── LogStream.tsx    # 实时事件日志流
│   │   │   ├── DebugPanel.tsx   # 可折叠调试日志面板
│   │   │   ├── ReviewView.tsx   # 人工审阅页面（补充信息 + 确认/跳过）
│   │   │   ├── ConfigPanel.tsx  # LLM 配置弹窗
│   │   │   ├── Toast.tsx        # 通知组件
│   │   │   └── ProjectForm.tsx  # 项目表单
│   │   ├── hooks/
│   │   │   └── useRunEvents.ts  # SSE hook（事件去重 + 回调 ref 化）
│   │   ├── test/
│   │   │   └── setup.ts        # 测试环境（gsap mock + EventSource mock）
│   │   ├── App.tsx             # 主应用（4 阶段状态机）
│   │   ├── App.test.tsx        # 前端测试
│   │   ├── styles.css          # 全局样式
│   │   └── main.tsx            # 入口
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── tests/                      # 后端测试
│   ├── api/
│   │   └── test_app.py         # API 端点集成测试
│   ├── graph/
│   │   └── test_research_workflow.py  # 工作流单元测试
│   └── unit/
│       ├── test_schemas.py     # Schema 验证测试
│       ├── test_sqlite_repository.py  # 数据库操作测试
│       ├── test_markdown_exporter.py  # 导出器测试
│       ├── test_openai_provider.py    # LLM provider 测试
│       ├── test_tavily_provider.py    # 搜索 provider 测试
│       ├── test_provider_contracts.py # Fake provider 测试
│       └── test_provider_factory.py   # 工厂函数测试
│
├── docs/                       # 项目文档
│   ├── 00-project-brief.md     # 项目简介与范围
│   ├── 01-architecture.md      # 架构设计（Gate + Supervisor）
│   ├── 02-agent-contracts.md   # Agent 合约（输入/输出/工具/禁止/失败）
│   ├── 03-state-and-storage.md # 状态与存储设计
│   ├── 04-provider-interfaces.md # 外部服务接口
│   ├── 05-api-contract.md      # API 契约
│   ├── 06-export-spec.md       # 导出规范
│   ├── 07-testing-strategy.md  # 测试策略
│   ├── 08-development-workflow.md # 开发流程
│   ├── 09-upgrade-roadmap.md   # 升级路线
│   ├── 10-current-status-and-handoff.md # 进度交接
│   ├── 11-tooling-handoff.md   # 工具交接
│   ├── 12-audit-gap-analysis.md # 对账报告
│   ├── 13-project-architecture.md # 本文档
│   ├── quickstart.md           # 快速启动指南
│   └── decisions/              # 架构决策记录
│       └── 0001-documentation-first-safety-architecture.md
│
├── SectorBreaker领域破壁设计稿.md  # 完整设计方法论（5 步 + Prompt）
├── CLAUDE.md                   # Claude Code 指令
├── AGENTS.md                   # 通用 AI Agent 指令
├── README.md                   # 项目 README
├── pyproject.toml              # Python 项目配置
├── environment.yml             # Conda 环境定义
└── .gitignore
```

## 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 前端 | Vite + React + TypeScript | 工作台 UI |
| 前端动画 | GSAP | 入场动画、流程图动效 |
| 前端通信 | EventSource (SSE) | 实时事件流 |
| 后端 | FastAPI + Python | API 服务 |
| 工作流 | LangGraph StateGraph | 多智能体编排 |
| 存储 | SQLite + FTS | 结构化数据 + 全文搜索 |
| LLM | OpenAI 兼容 API | 任意 LLM 提供商 |
| 搜索 | Tavily | 网络搜索（可替换） |
| 导出 | Markdown | Obsidian 兼容知识库 |

---

## LangGraph 业务架构

### 整体流程

```
用户输入领域名称
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph Workflow Engine                     │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐                │
│  │  scope   │──▶│ evidence │──▶│research_frame│                │
│  │ 范围确认  │   │ 证据收集  │   │  研究框架     │                │
│  └────┬─────┘   └──────────┘   └──────┬───────┘                │
│       │ 🔴暂停                         │ 🔴暂停                  │
│       │                               │                         │
│       ▼                               ▼                         │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              knowledge_map 知识地图                    │       │
│  │  ┌────────────┐ ┌────────────┐ ┌──────────────────┐  │       │
│  │  │ 行业地图    │ │ 市场现状    │ │ 玩家与交易单位    │  │       │
│  │  ├────────────┤ ├────────────┤ ├──────────────────┤  │       │
│  │  │ 内容与渠道  │ │ 交易单位DB  │ │ 竞品数据库       │  │       │
│  │  ├────────────┤ ├────────────┤ ├──────────────────┤  │       │
│  │  │ 收入结构    │ │ 信任资产    │ │ 内容账号DB       │  │       │
│  │  ├────────────┤ ├────────────┤ ├──────────────────┤  │       │
│  │  │ 高频选题    │ │ 知识卡片    │ │                  │  │       │
│  │  └────────────┘ └────────────┘ └──────────────────┘  │       │
│  │         11 个产物并行生成（semaphore 限制并发 3）       │       │
│  └──────────────────────────────────────────────────────┘       │
│       │                                                         │
│       ▼                                                         │
│  ┌──────────────┐   ┌───────────┐   ┌──────────┐               │
│  │  opportunity │──▶│qa_critic  │──▶│  export  │               │
│  │  机会地图     │   │ 质量门检查 │   │ 导出知识库│               │
│  └──────┬───────┘   └───────────┘   └──────────┘               │
│         │ 🔴暂停                                                 │
└─────────┼───────────────────────────────────────────────────────┘
          │
          ▼
   ┌─────────────┐
   │ Obsidian    │
   │ 知识库导出   │
   └─────────────┘

🔴 = 人工审阅暂停点（scope / research_frame / opportunity）
```

### Gate 详解

| Gate | Agent | 输入 | 输出（产物） | 暂停 |
|------|-------|------|-------------|------|
| scope | Research Planner | 用户领域名称 | 研究范围分析（边界、关键问题、数据口径） | ✅ |
| evidence | Search Scout | 领域关键词 | 搜索证据（网络来源） | ❌ |
| research_frame | Research Planner | 领域 + 证据 | 研究框架（板块、问题、路径） | ✅ |
| knowledge_map | Knowledge Mapper | 全部前置数据 | 11 个产物（并行生成） | ❌ |
| opportunity | Opportunity Analyst | 全部产物 | 机会地图（假设、验证路径） | ✅ |
| qa_critic | QA Critic | 全部产物 | 质量检查结果 | ❌ |
| export | Export Writer | 全部产物 | Obsidian Markdown 文件 | ❌ |

### 产物清单（15 种 ArtifactType）

| # | ID | 类型 | 内容 |
|---|-----|------|------|
| 1 | ART-SCOPE-ANALYSIS | research_frame | 领域边界、关键问题、数据口径 |
| 2 | ART-RESEARCH-FRAME | research_frame | 研究板块、关键问题、学习路径 |
| 3 | ART-INDUSTRY-MAP | industry_map | 三级节点地图 + 学习顺序 |
| 4 | ART-MARKET-OVERVIEW | market_overview | 市场规模、增长、细分、可信度 |
| 5 | ART-PLAYER-MAP | player_map | 7 类角色 + 代表玩家 + 交易单位 |
| 6 | ART-CONTENT-CHANNELS | content_channels | 关键词/平台/内容分类/转化路径 |
| 7 | ART-TRANSACTION-UNITS | transaction_units | 交易单位 × 11 个字段 |
| 8 | ART-COMPETITOR-ANALYSIS | competitor_analysis | 5-10 玩家逐一分析 13 维度 |
| 9 | ART-REVENUE-STRUCTURE | revenue_structure | 引流/转化/利润/复购产品 |
| 10 | ART-TRUST-ASSETS | trust_assets | 信任建立 7 维度分析 |
| 11 | ART-CONTENT-ACCOUNTS | content_accounts | 按平台的内容账号数据库 |
| 12 | ART-CONTENT-TOPICS | content_topics | 高频选题 7 维度分析 |
| 13 | ART-KNOWLEDGE-CARD | export_manifest | Obsidian 知识卡片模板 |
| 14 | ART-OPPORTUNITY-MAP | opportunity_map | 机会假设 + 验证路径 |
| 15 | — | — | scope_analysis 存为 research_frame 类型 |

### 暂停/恢复机制

```
                    ┌─────────────────┐
                    │ run_project API  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ BackgroundTasks │
                    │ run_workflow_   │
                    │ until_pause()   │
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │  执行 Gate → 检查是否暂停    │
              │  if gate in HUMAN_REVIEW:   │
              │    emit waiting_for_human   │
              │    save workflow_state      │
              │    return (paused)          │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  SSE: GET /runs/{id}/events │
              │  → 重播已有事件              │
              │  → 轮询新事件               │
              │  → 收到 waiting_for_human   │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  前端: ReviewView 显示       │
              │  用户补充信息 / 跳过          │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  POST /runs/{id}/resume     │
              │  → 加载 workflow_state      │
              │  → 读取 user_inputs        │
              │  → 从下一个 Gate 继续执行    │
              └─────────────────────────────┘
```

### 前端状态机

```
landing ──▶ researching ──▶ reviewing ──▶ researching ──▶ ... ──▶ reviewing ──▶ result
   │             │              │                                  │
   │             │              │                                  │
   │         SSE 事件流     waiting_for_human               最终审阅
   │         实时更新        中间审阅页面                    (export gate)
   │                                                   
   │                                                         
   └─ LLM 设置     └─ 流程图 + 日志     └─ 补充信息 + 确认     └─ 产物/证据/问答/导出
```

### 数据库 Schema

```
projects
├── id, title, domain, market_scope, depth, status
│
├── evidence
│   ├── id, project_id, source_title, source_url
│   ├── snippet, summary, confidence, verification_status
│   └── FTS 索引 (evidence_fts)
│
├── artifacts
│   ├── id, project_id, artifact_type, title
│   ├── content_path, content, source_evidence_ids
│   └── schema_version, created_at
│
├── runs
│   ├── id, project_id, status, current_gate
│   ├── workflow_state (JSON, 暂停/恢复用)
│   └── created_at, completed_at
│
├── run_events
│   ├── id (autoincrement), run_id
│   ├── event_type, gate, step, agent, message, data
│   └── created_at
│
└── user_inputs
    ├── id, run_id, gate, input_type, content
    └── created_at
```
