# SectorBreaker 全面重构方案

## 背景

设计稿（SectorBreaker领域破壁设计思路.md）定义了 5 大步、20+ 子步骤的研究流程，但后端 LangGraph workflow 只实现了 6 个粗糙的 gate，其中大部分是硬编码模板。前端只是一个静态仪表盘。本次重构的目标是让设计稿的完整研究流程在前后端真正落地。

---

## Phase 0：Bug 修复 + 基础设施

### 0.1 修复启动研究 API 报错

**根因**：`run_project` 是同步端点，内部调用 `asyncio.run()` 执行异步 provider，在 FastAPI 线程池中事件循环冲突。

**修复**：
- `app.py` 的 `run_project` 改为 `async def`
- workflow 内部 provider 调用改为 `await`（workflow 改为 async graph）
- 添加错误处理和日志

### 0.2 后端：Run 模型 + 数据库表

新增 `ResearchRun` 表：

```sql
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/running/waiting/completed/failed
    current_gate TEXT,
    current_step TEXT,
    created_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
```

新增 `RunEvent` 表（SSE 事件持久化）：

```sql
CREATE TABLE run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,   -- gate_start/step_start/step_complete/artifact_created/evidence_collected/gate_complete/waiting_for_human/error
    gate TEXT,
    step TEXT,
    agent TEXT,
    message TEXT,
    data TEXT,                  -- JSON
    created_at TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
```

新增 `UserInput` 表（用户补充信息）：

```sql
CREATE TABLE user_inputs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    gate TEXT NOT NULL,
    input_type TEXT NOT NULL,   -- note/guidance/evidence_data
    content TEXT NOT NULL,      -- 文字内容或 JSON 数据
    created_at TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
```

### 0.3 后端：SSE 事件流端点

```
POST /api/projects/{project_id}/runs          → 创建 run，后台启动，返回 run_id
GET  /api/runs/{run_id}                       → 查询 run 状态
GET  /api/runs/{run_id}/events                → SSE 流式事件
POST /api/runs/{run_id}/resume                → 用户确认后恢复（可携带补充信息）
POST /api/runs/{run_id}/inputs                → 用户提交补充信息
```

---

## Phase 1：后端 Workflow 重构（按设计稿）

### 1.1 设计稿 vs 当前实现的差距

| 设计稿步骤 | 当前实现 | 差距 |
|-----------|---------|------|
| 1.1 确认研究什么（10个问题） | 无 | 缺失 |
| 1.2 建立市场数据库 | evidence_gate 泛搜索 | 没有结构化市场数据 |
| 1.3 建立玩家数据库 | knowledge_map_gate 硬编码 | 没有真实玩家分析 |
| 1.4 建立交易单位数据库 | knowledge_map_gate 硬编码 | 没有交易单位拆解 |
| 2.1 建立竞品数据库 | 无 | 缺失 |
| 2.2 拆解收入结构 | 无 | 缺失 |
| 2.3 拆解转化路径 | 无 | 缺失 |
| 2.4 拆解信任资产 | 无 | 缺失 |
| 2.5 拆解价格/关键词/渠道 | 无 | 缺失 |
| 3.1 内容账号数据库 | 无 | 缺失（需要人参与） |
| 3.2 高频选题分析 | 无 | 缺失 |
| 3.3 内容分类 | 无 | 缺失 |
| 4.1 行业地图（2层） | knowledge_map_gate 硬编码 | 没有真实拆解 |
| 4.2 知识卡片 | 无 | 缺失 |
| 4.3 机会地图 | opportunity_gate 硬编码 | 没有真实分析 |

### 1.2 重构后的 Gate 结构

保留 6 个 gate 的宏观结构，但每个 gate 内部有多个子步骤（step），每个 step 对应一个专业 Agent。

```
Gate 1: Scope（范围确认）
  └─ Step 1.1: 确认研究范围 + 生成 10 个关键问题
  └─ 🔒 人工审查：用户确认/修改范围，可补充已有认知

Gate 2: Database（建数据库）    ← 原 evidence_gate 扩展
  └─ Step 2.1: Search Scout 搜索行业概况
  └─ Step 2.2: Market Mapper 建立市场数据库
  └─ Step 2.3: Player Analyst 建立玩家数据库
  └─ Step 2.4: Transaction Analyst 建立交易单位数据库
  └─ 🔒 人工审查：用户可补充市场数据、玩家信息、交易单位

Gate 3: Reverse Engineering（反向拆解）  ← 新增 gate
  └─ Step 3.1: Player Analyst 竞品数据库
  └─ Step 3.2: Transaction Analyst 收入结构拆解
  └─ Step 3.3: Content Analyst 转化路径分析
  └─ Step 3.4: Evidence Curator 信任资产识别
  └─ Step 3.5: Content Analyst 价格/关键词/渠道
  └─ 🔒 人工审查：用户可补充竞品信息、行业经验

Gate 4: Content Ecosystem（内容生态）  ← 新增 gate
  └─ Step 4.1: Content Analyst 内容账号数据库
  └─ Step 4.2: Content Analyst 高频选题分析
  └─ Step 4.3: Content Analyst 内容分类
  └─ 🔒 人工审查：⚠️ 重点！账号数据 AI 难以爬取，需要人补充

Gate 5: Knowledge Map（知识地图）  ← 原 knowledge_map_gate 重构
  └─ Step 5.1: Knowledge Mapper 行业地图（一级+二级）
  └─ Step 5.2: Knowledge Mapper 知识卡片生成
  └─ Step 5.3: Opportunity Analyst 机会地图
  └─ 🔒 人工审查：用户确认地图结构，补充机会假设

Gate 6: Export（导出）
  └─ Step 6.1: QA Critic 质量检查
  └─ Step 6.2: Export Writer 写入 Obsidian 包
  └─ ✅ 完成
```

### 1.3 Agent 职责重新定义

| Agent | 负责的 Step | 输入 | 输出 |
|-------|-----------|------|------|
| Research Planner | 1.1 | 用户领域+范围 | 10 个关键问题 + 学习路径 |
| Search Scout | 2.1 | 搜索任务 | 来源候选列表 |
| Market Mapper | 2.2 | 搜索结果+用户补充 | 结构化市场数据 |
| Player Analyst | 2.3, 3.1 | 搜索结果+用户补充 | 玩家角色+竞品结构 |
| Transaction Analyst | 2.4, 3.2 | 搜索结果+用户补充 | 交易单位+收入结构 |
| Content Analyst | 3.3, 3.5, 4.1-4.3 | 搜索结果+用户补充 | 转化路径+内容生态 |
| Evidence Curator | 3.4 | 所有中间结果 | 信任资产+证据标注 |
| Knowledge Mapper | 5.1, 5.2 | 所有证据+研究框架 | 行业地图+知识卡片 |
| Opportunity Analyst | 5.3 | 知识地图+所有证据 | 机会假设+验证路径 |
| QA Critic | 6.1 | 所有产物 | 质量报告 |
| Export Writer | 6.2 | 已审核产物 | Obsidian 包 |

### 1.4 人工审查机制

每个 gate 完成后，workflow 发射 `waiting_for_human` 事件并暂停。

用户在审查页面可以：
1. **查看 Agent 产出**：每个 step 的结果摘要
2. **添加指导备注**（`input_type: guidance`）：告诉 AI 下一步研究偏向什么
   - 例："重点研究轻医美市场，忽略手术类"
   - 例："关注下沉市场机会"
3. **注入结构化数据**（`input_type: evidence_data`）：用户自己的数据直接进入证据库
   - 例：用户粘贴的竞品价格表
   - 例：用户搜集的小红书账号列表
   - 例：用户已有的行业报告摘要
4. **确认继续** 或 **要求重新搜索**

用户补充的内容通过 `POST /api/runs/{run_id}/resume` 提交，workflow 恢复时会读取这些输入，将 `evidence_data` 转为 `EvidenceItem` 注入，将 `guidance` 传给下一步 Agent 的 prompt。

### 1.5 后端文件变更

| 文件 | 变更 |
|------|------|
| `backend/app/schemas/state.py` | 新增 RunStatus、RunEvent、UserInput |
| `backend/app/schemas/evidence.py` | 新增 `source_type: "user_input"` |
| `backend/app/graph/workflow.py` | 全面重构：6 gates × 多 steps，async，事件发射 |
| `backend/app/graph/agents.py` | 新建：每个 Agent 的实际逻辑（调用 LLM/Search） |
| `backend/app/api/app.py` | 新增 runs/events/resume/inputs 端点 |
| `backend/app/storage/sqlite.py` | 新增 runs/events/user_inputs 表和 CRUD |

---

## Phase 2：前端基础设施

### 2.1 新增依赖

```json
{
  "gsap": "^3.12"
}
```

### 2.2 文件结构

```
frontend/src/
├── App.tsx                     # 状态机：landing → researching → reviewing → result
├── main.tsx
├── styles.css                  # 全局样式 + CSS 变量
├── api/
│   └── client.ts               # 类型安全的 API 客户端
├── components/
│   ├── Logo.tsx                # 知识网络 Logo (SVG + GSAP)
│   ├── LandingView.tsx         # 首页
│   ├── ResearchView.tsx        # 运行中主视图
│   ├── ReviewView.tsx          # 人工审查页面（独立页面，非弹窗）
│   ├── ResultView.tsx          # 完成态
│   ├── GraphFlow.tsx           # LangGraph 流程图 (SVG)
│   ├── LogStream.tsx           # 实时日志面板
│   ├── AgentCard.tsx           # Agent 工作卡片
│   ├── StepDetail.tsx          # Step 展开详情
│   ├── UserInputForm.tsx       # 用户补充信息表单
│   ├── Toast.tsx               # 通知（保留）
│   └── ConfigPanel.tsx         # LLM 设置（保留）
└── hooks/
    ├── useRunEvents.ts         # SSE 事件订阅
    └── useGsap.ts              # GSAP 动画
```

---

## Phase 3：前端页面实现

### 3.1 LandingView（首页）

- 全屏居中，极简
- Logo（知识网络风格，GSAP 节点动画）
- "你想了解什么领域？" + 大输入框
- "开始破壁" 按钮
- 底部 6 个 gate 的流程预览条
- 右下角 LLM 设置

### 3.2 ResearchView（运行中）

核心布局：

```
┌─────────────────────────────────────────────┐
│  Logo   领域名   ● 运行中                    │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─ LangGraph 流程图 ──────────────────┐   │
│  │                                      │   │
│  │  ┌───┐    ┌───┐    ┌───┐            │   │
│  │  │ 1 │───▶│ 2 │───▶│ 3 │───▶ ...   │   │
│  │  └───┘    └───┘    └───┘            │   │
│  │   ✓       ●⚡       ○               │   │
│  │          [数据]    [等待]            │   │
│  │                                      │   │
│  │  当前 Gate 展开：                    │   │
│  │  ┌─────────────────────────────┐    │   │
│  │  │ Gate 2: 建数据库            │    │   │
│  │  │  ✅ 搜索行业概况            │    │   │
│  │  │  ●⚡ 建立市场数据库         │    │   │
│  │  │  ○ 建立玩家数据库           │    │   │
│  │  │  ○ 建立交易单位数据库       │    │   │
│  │  └─────────────────────────────┘    │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  ┌─ 实时日志 ─────────────────────────┐    │
│  │ 10:23:01 [Search Scout] 搜索中...  │    │
│  │ 10:23:03 [Search Scout] 找到 5 条  │    │
│  │ 10:23:04 [Market Mapper] 分析中... │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─ 当前 Agent ───────────────────────┐    │
│  │  📊 Market Mapper                   │    │
│  │  正在整理市场规模、增长驱动、限制... │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

- 流程图节点：SVG + GSAP 状态动画
- 日志流：GSAP 行动画（右滑入+淡入）
- Agent 卡片：GSAP 弹入弹出
- Gate 完成时：节点变绿 + 轻微庆祝动画 → 自动进入 ReviewView

### 3.3 ReviewView（人工审查，独立页面）

每个 gate 完成后进入，不是弹窗。

```
┌─────────────────────────────────────────────┐
│  Logo   Gate 2 完成：建数据库                 │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─ Agent 产出摘要 ─────────────────────┐  │
│  │                                      │  │
│  │  📊 市场数据库                       │  │
│  │  • 市场规模：约 500 亿               │  │
│  │  • 增长率：15% YoY                   │  │
│  │  • 核心驱动：消费升级、政策利好       │  │
│  │                                      │  │
│  │  👥 玩家数据库                       │  │
│  │  • 全国连锁 3-5 家                   │  │
│  │  • 区域机构 200+                     │  │
│  │  • 新兴品牌 快速增长                 │  │
│  │                                      │  │
│  │  💰 交易单位                         │  │
│  │  • 注射类：客单 2000-8000            │  │
│  │  • 光电类：客单 500-3000             │  │
│  │  ...                                 │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  ┌─ 补充信息（可选）────────────────────┐  │
│  │                                      │  │
│  │  📝 研究方向备注                     │  │
│  │  ┌─────────────────────────────┐    │  │
│  │  │ 例：重点研究下沉市场，      │    │  │
│  │  │ 忽略一线城市高端机构...     │    │  │
│  │  └─────────────────────────────┘    │  │
│  │                                      │  │
│  │  📊 已有数据/信息                    │  │
│  │  ┌─────────────────────────────┐    │  │
│  │  │ 粘贴你的数据、表格、报告    │    │  │
│  │  │ 摘要等，会作为证据注入      │    │  │
│  │  └─────────────────────────────┘    │  │
│  │                                      │  │
│  │  💡 提示：如果你在这个领域有经验，   │  │
│  │  补充的信息会帮助 AI 更精准地研究    │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  [跳过，直接继续]        [确认并继续 →]     │
└─────────────────────────────────────────────┘
```

- Agent 产出用卡片展示，带 GSAP 淡入动画
- 用户补充区两个输入：方向备注（textarea）+ 已有数据（大 textarea）
- 两个按钮：跳过（不补充直接继续）/ 确认（携带补充信息继续）
- 特殊 gate（如内容生态）的提示文案强调"账号数据建议手动补充"

### 3.4 ResultView（完成态）

```
┌─────────────────────────────────────────────┐
│  Logo   AI Agent 工具   ✅ 研究完成          │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─ 流程图（全部完成）──────────────────┐  │
│  │  ✓ ── ✓ ── ✓ ── ✓ ── ✓ ── ✓        │  │
│  │  点击任意节点查看该阶段产物           │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  ┌─ 选中节点详情 ───────────────────────┐  │
│  │  Gate 2: 建数据库                    │  │
│  │  ┌─ 市场数据库 ──────────────────┐  │  │
│  │  │  产物内容预览...               │  │  │
│  │  └────────────────────────────────┘  │  │
│  │  ┌─ 玩家数据库 ──────────────────┐  │  │
│  │  │  产物内容预览...               │  │  │
│  │  └────────────────────────────────┘  │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  ┌─ 证据来源 ───────────────────────────┐  │
│  │  • EV-001: 行业报告 (AI搜集)         │  │
│  │  • EV-002: 用户补充的竞品数据         │  │
│  │  • EV-003: 用户补充的小红书账号       │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  ┌─ 项目问答 ───────────────────────────┐  │
│  │  [输入框]                    [询问]   │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  [导出知识库]          [新研究]             │
└─────────────────────────────────────────────┘
```

### 3.5 Logo 设计

知识网络风格 SVG：
- 3-4 个大小不一的圆形节点
- 节点之间用贝塞尔曲线连接
- 主色 `#106b5d`，辅助色 `#2d5d9f`
- GSAP 动画：页面加载时节点依次出现 → 连线绘制 → 整体微弱呼吸脉冲

### 3.6 GSAP 动画清单

| 元素 | 动画 | 触发时机 |
|------|------|---------|
| Logo 节点 | 依次缩放出现 + 连线 drawSVG | 页面加载 |
| Landing → Research | 整页上滑淡出 / 下滑淡入 | 点击"开始破壁" |
| 流程图节点状态 | 颜色渐变 + 脉冲 | SSE 事件 |
| 流程图连线 | 渐变色流动 | 前一个节点完成 |
| 日志新行 | x:20→0 + opacity:0→1 | 新事件到达 |
| Agent 卡片 | y:30→0 + scale:0.95→1 | 新 agent 启动 |
| Review 产出卡片 | stagger 淡入 | 进入审查页 |
| 完成庆祝 | 节点依次变绿 + 轻微粒子 | 全部完成 |

---

## Phase 4：测试 + 验证

### 4.1 验证清单

- [ ] `python -m pytest -q` 全部通过
- [ ] `cd frontend && npm test` 全部通过
- [ ] `cd frontend && npm run build` 构建成功
- [ ] 手动测试：输入领域 → 流程图逐步推进 → 审查页补充信息 → 继续 → 完成
- [ ] SSE 事件正确流式推送
- [ ] 用户补充信息正确注入为 EvidenceItem
- [ ] Logo 动画正常
- [ ] 人工审查页面正确暂停和恢复
- [ ] 导出的 Obsidian 包含用户补充的证据

---

## 实施顺序总结

| Phase | 内容 | 预估工作量 |
|-------|------|-----------|
| Phase 0 | Bug 修复 + Run 模型 + SSE 端点 | 后端基础设施 |
| Phase 1 | Workflow 重构：6 gates × 多 steps + 人工审查机制 | 后端核心 |
| Phase 2 | 前端基础设施：gsap + API client + SSE hook + Logo | 前端基础 |
| Phase 3 | 前端 4 个视图 + GSAP 动画 | 前端核心 |
| Phase 4 | 测试 + 验证 + 修复 | 收尾 |
