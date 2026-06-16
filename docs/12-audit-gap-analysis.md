# SectorBreaker MVP 对账报告：设计稿 vs 代码实现

> 生成时间：2026-06-16
> 目的：逐项核对设计稿与代码实现的差距，定位 MVP 跑不通的阻塞点

---

## 阻塞 MVP 的关键问题（必须先修）

### 🔴 B1：用户注入的信息不影响后续 Gate

**设计稿要求**：每个 gate 完成后暂停，用户可以补充信息，补充的信息会影响后续 gate 的 AI 分析。

**代码现状**：
- `ReviewView` 的 `onContinue` 提交 `guidance` 和 `evidenceData` 到后端 `addUserInput` API ✅
- 后端 `addUserInput` 只是存到 `user_inputs` 表 ❌
- `workflow.py` 的 `run_research_workflow` 接收 `user_guidance` 和 `user_evidence_items` 参数 ✅
- **但 workflow 从不读取 `user_inputs` 表** ❌
- **而且 workflow 一口气跑完所有 gate，根本不会暂停等人审** ❌

**结论**：人工审阅是假的。ReviewView 只在全部完成后显示一次，用户补充的信息永远不会被用到。

### 🔴 B2：workflow 不暂停，ReviewView 只在最后出现一次

**设计稿要求**：每个关键节点暂停等待确认。

**代码现状**：
- `App.tsx` 的 phase 状态机：`landing → researching → reviewing → result`
- `reviewing` 只在 `onComplete`（SSE [DONE]）后触发一次
- workflow 中没有 `waiting_for_human` 事件，没有暂停机制
- 6 个 gate 一口气跑完

**结论**：用户无法在中间节点审阅和注入信息。

### 🔴 B3：LLM timeout 可能不够

**代码现状**：`OpenAICompatibleLLMProvider.timeout_seconds = 60`

**问题**：现在每个 gate 调 LLM 1-4 次。knowledge_map_gate 连续调 4 次 LLM，如果每次 30-60 秒，整个 gate 可能需要 2-4 分钟。但 timeout 是单次请求的，应该没问题。

**实际风险**：某些 LLM API（如本地 Ollama）可能很慢，60 秒不够。但这不是 MVP 阻塞项。

### 🔴 B4：SSE 事件流在 workflow 极快完成时的行为

**代码现状**：
- `run_project` 用 `BackgroundTasks` 后台执行，立即返回 run ID
- 前端拿到 runId 后连接 SSE
- SSE endpoint 先重播已有事件，然后轮询新事件

**风险**：如果 workflow 在前端连接 SSE 之前就完成了，SSE 会重播所有事件然后发 [DONE]。这应该能正常工作，但需要验证。

---

## 第一步：建立行业数据库

### 1.1 确认研究什么

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 10 个关键问题 | scope_gate 调 LLM 分析边界 | ⚠️ LLM prompt 要求输出 common_confusions，但不要求 10 个问题 |
| 数据口径调查 | 无专门产物 | ❌ 缺失 |
| 每个问题说明为什么重要、去哪找、常见误判 | 无 | ❌ 缺失 |

### 1.2 建立市场数据库

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 市场规模 | MARKET_OVERVIEW artifact，LLM prompt 要求"市场规模估算" | ⚠️ 有，但字段不够详细 |
| 增长速度 | prompt 提到"增长驱动" | ⚠️ 简略 |
| 核心细分市场用户规模 | 无 | ❌ 缺失 |
| 供给规模 | 无 | ❌ 缺失 |
| 数据来源、统计口径、可信度 | prompt 提到"数据口径说明" | ⚠️ 有要求但不确定 LLM 是否会输出 |
| 区分事实、推测和观点 | prompt 提到"区分事实、推测和观点" | ✅ 有要求 |

### 1.3 建立玩家数据库

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 按角色分类（7 类角色） | PLAYER_MAP prompt 要求按角色分类 | ✅ 有 |
| 每类给出代表玩家 | prompt 要求"代表玩家" | ✅ 有 |
| 商业价值、议价能力 | prompt 要求"商业价值、议价能力" | ✅ 有 |
| 新手容易忽略的地方 | 无 | ❌ 缺失 |

### 1.4 建立交易单位数据库

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 交易单位名称 | PLAYER_MAP prompt 提到"识别主要交易单位" | ⚠️ 合并在玩家里，不独立 |
| 客单价区间 | 无 | ❌ 缺失 |
| 购买频率、复购周期 | 无 | ❌ 缺失 |
| 交付难度、风险点、毛利来源 | 无 | ❌ 缺失 |
| 内容卖点、用户评价关键词 | 无 | ❌ 缺失 |

**注意**：`ArtifactType.TRANSACTION_UNITS` 枚举已定义但从未在 workflow 中使用。

---

## 第二步：反向拆解此行业怎么赚钱

### 2.1 建立竞品数据库

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 逐一分析 10-20 个玩家 | 无 | ❌ 完全缺失 |
| 每个玩家 11 个维度分析 | 无 | ❌ 完全缺失 |
| 定位、目标用户、主推产品 | 无 | ❌ |
| 价格结构、获客渠道、转化路径 | 无 | ❌ |
| 信任资产、复购机制、内容策略 | 无 | ❌ |
| 差异化优势、潜在风险 | 无 | ❌ |

**结论**：第二步整体缺失。没有专门的 gate 或 artifact。

### 2.2 拆解收入结构

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 引流产品、转化产品、利润产品、复购产品 | 无 | ❌ 完全缺失 |
| 每类 7 个字段 | 无 | ❌ |

### 2.3 拆解转化路径

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 从内容到成交的完整路径 | CONTENT_CHANNELS prompt 提到"转化路径分析" | ⚠️ 简略提及 |
| 流程图和关键页面清单 | 无 | ❌ 缺失 |

### 2.4 拆解信任资产

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 用户最担心什么 | 无专门分析 | ❌ 缺失 |
| 哪些证据最有说服力 | 无 | ❌ |
| 新进入者最缺哪类信任资产 | 无 | ❌ |

### 2.5 拆解价格、关键词和渠道

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 价格区间、低价引流、主流成交价格 | 无 | ❌ 缺失 |
| 6 类关键词 | CONTENT_CHANNELS prompt 提到"搜索关键词分类" | ⚠️ 简略 |
| 6 类渠道 | prompt 提到"内容平台、本地生活、私域" | ⚠️ 部分 |

---

## 第三步：研究内容生态

### 3.1 建立内容账号数据库

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 批量整理账号 | 无 | ❌ 完全缺失 |
| 8 个平台 | 无 | ❌ |
| 10 个输出字段 | 无 | ❌ |

### 3.2 找出高频选题

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 反复出现的选题 | 无 | ❌ 完全缺失 |
| 用户反复提问的问题 | 无 | ❌ |
| 收藏率/转化率分析 | 无 | ❌ |

### 3.3 给内容分类

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 6 种类型（曝光/信任/收藏/转化/案例/专家IP） | CONTENT_CHANNELS prompt 提到 4 种 | ⚠️ 缺案例型和专家IP型 |
| 每类说明典型标题、用户行为 | 无详细要求 | ❌ |

---

## 第四步：建立领域知识地图

### 4.1 行业地图

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 一级/二级/三级目录 | INDUSTRY_MAP prompt 要求一级+二级节点 | ⚠️ 缺三级 |
| 标注供给侧/需求侧/渠道/风险 | prompt 有要求 | ✅ |
| 新手最容易误解的 10 个地方 | 无 | ❌ 缺失 |

### 4.2 新手学习顺序

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 先学什么后学什么 | 无专门产物 | ❌ 缺失 |
| 每个节点 3 个关键问题 | 无 | ❌ |
| 每个节点生成 Obsidian 知识卡片 | 无 | ❌ |

### 4.3 细化边界理解

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 每个一级节点拆到第二层 | INDUSTRY_MAP prompt 有二级节点 | ⚠️ 有二级但不够深 |
| 每个二级节点：定义、关系、关键玩家、关键指标、常见误区 | 无详细要求 | ❌ |

### 4.4 知识卡片

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| Obsidian 知识卡片模板 | MarkdownExporter 输出 Obsidian frontmatter | ⚠️ 有基础格式 |
| 节点名称、定义、关系、关键事实、指标、玩家、案例、误区、待验证、来源 | 无结构化模板 | ❌ |

### 4.5 机会地图

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 基于前面所有数据 | OPPORTUNITY_MAP prompt 传入 artifact_titles 和 evidence_count | ⚠️ 有引用但不够详细 |
| 7 个分析维度 | prompt 要求"机会逻辑、目标用户、进入门槛、资源、风险、验证" | ⚠️ 缺"增长快/竞争激烈"等维度 |
| 每个假设 7 个字段 | prompt 有要求 | ✅ 基本覆盖 |

---

## 第五步：让数据持续成长

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 信息源数据库 | 无 | ❌ V2/V3 |
| 监控系统 | 无 | ❌ V2/V3 |
| 周报生成 | 无 | ❌ V2/V3 |

**结论**：第五步明确是 V2/V3 范围，不需要在 MVP 实现。

---

## 人工审阅机制

| 设计稿要求 | 代码实现 | 状态 |
|-----------|---------|------|
| 用户确认或编辑框架 | ReviewView 有 guidance 输入框 | ⚠️ UI 有但数据不用 |
| 用户审阅阶段输出 | ReviewView 显示事件和产物 | ⚠️ 只在最后显示一次 |
| 每个关键节点暂停 | workflow 从不暂停 | ❌ 严重缺失 |
| 一键执行选项 | 无 | ❌ 缺失 |
| 注入信息影响后续 gate | user_inputs 存表但 workflow 不读 | ❌ 严重缺失 |

---

## 前端状态机分析（审计补充）

### 当前流程
```
landing → researching → reviewing → result（单向，不可逆）
```

### 前端精确问题清单

| ID | 严重度 | 位置 | 问题 |
|----|--------|------|------|
| F-D | P0 | App.tsx:415 | ReviewView 只在 workflow 全部完成后显示一次，`completedGate` 硬编码为 `"export"` |
| F-E | P0 | ReviewView.tsx:90 | 用户输入 guidance/evidence 存表但 workflow 不读取 |
| F-F | P0 | App.tsx:519 | onContinue/onSkip 只 `setPhase("result")`，不触发后续 gate |
| F-B | P1 | App.tsx:148 | SSE 断开后前端卡在 researching，无错误状态显示 |
| F-L | P1 | App.tsx:175 | ResearchView 始终显示"研究进行中"，不根据 isConnected 切换 |
| F-C | P2 | app.py:166 | SSE 5 分钟 idle 超时，长任务可能断开 |
| F-G | P2 | App.tsx:408 | artifacts/evidence 获取可能有竞态（[DONE] 和数据写入的时序） |
| F-A | P2 | App.tsx:148 | currentGate 追踪依赖事件质量，gate 字段缺失时回退 scope |
| F-I | P3 | App.tsx:90 | isLoading 无超时兜底，后端不响应时按钮永久"启动中" |
| F-K | P3 | App.tsx:435 | startRun 失败时 project 已创建但未清理（孤儿数据） |
| F-M | P3 | ReviewView.tsx:111 | addUserInput 失败时静默 continue，用户不知保存失败 |

### 需要改为
```
landing → researching → [gate_complete事件] → reviewing → [用户确认/跳过]
    → [调用resume API] → researching → ... → [所有gate完成] → result
```

---

## 后端数据流分析

### 正常路径
1. `POST /api/projects` → 创建项目 ✅
2. `POST /api/projects/{id}/runs` → 创建 run，BackgroundTasks 启动 workflow ✅
3. `GET /api/runs/{id}/events` → SSE 重播 + 轮询新事件 ✅
4. workflow 完成 → `run.status=completed` → SSE 发 `[DONE]` ✅
5. `GET /artifacts`, `/evidence` → 获取结果 ✅
6. `POST /exports` → 导出 Markdown ✅

### 后端精确问题清单

| ID | 严重度 | 位置 | 问题 |
|----|--------|------|------|
| B-1 | P0 | workflow.py | workflow 不暂停，`WAITING_FOR_human` 状态从未使用 |
| B-2 | P0 | app.py:200 | `/resume` 端点只存数据，不触发后续 workflow |
| B-3 | P0 | workflow.py:65 | `run_research_workflow` 一次性跑完，无法中途暂停恢复 |
| B-4 | P1 | app.py:127 | workflow 异常时 SSE 可能不发 `[DONE]`，前端卡住 |
| B-5 | P1 | openai_compatible.py:45 | timeout=60s 对某些 LLM API 可能不够 |
| B-6 | P1 | app.py:166 | SSE max_idle=600（5 分钟），长任务超时断开 |
| B-7 | P2 | sqlite.py | SQLite 无 WAL 模式，并发写可能锁死 |
| B-8 | P2 | workflow.py | knowledge_map_gate 连续 4 次 LLM 调用，无进度细分事件 |
| B-9 | P2 | app.py:114 | BackgroundTasks 异常被 catch 但 SSE 可能已超时 |

### 断裂点总结
1. **workflow 中间不暂停**：步骤 3 一次性收到所有事件，没有人工审阅窗口
2. **用户输入不回流**：`/resume` 只存表，不读取 user_inputs 注入 workflow
3. **失败处理不完整**：workflow 失败 → run=failed → 但 SSE 轮询可能已超时断开
4. **无法恢复执行**：LangGraph `ainvoke` 一次性跑完，不支持 checkpoint 暂停恢复

---

## 总结：差距优先级

### P0 — MVP 阻塞项（必须修复）
1. **workflow 暂停机制**：每个 gate 完成后暂停，发 `waiting_for_human` 事件
2. **前端 gate-by-gate 审阅**：收到 `gate_complete` 事件后切到 reviewing，用户确认后 resume
3. **用户信息回流**：workflow 恢复时读取 user_inputs，注入到后续 gate 的 LLM prompt
4. **失败状态处理**：workflow 失败时前端正确显示错误，不卡住

### P1 — 功能完整性（应该修复）
5. **第二步缺失**：竞品数据库、收入结构、转化路径、信任资产（需新增 gate 或扩展现有 gate）
6. **第三步缺失**：内容账号数据库、高频选题、内容分类（需新增产物类型）
7. **交易单位独立产物**：`TRANSACTION_UNITS` 已定义但未使用

### P2 — 质量提升（可以后续）
8. LLM prompt 更详细，要求更多输出字段
9. 行业地图三级节点
10. 知识卡片结构化模板
11. 一键执行选项（跳过所有审阅）
