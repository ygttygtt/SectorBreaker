# Agent Kernel 架构设计文档

> 本文档描述 SectorBreaker V2 Agent Kernel 的状态机、上下文管理、记忆系统和 Agent 设计。
> 面向想了解项目整体运作方式的开发者或产品负责人。

---

## 1. 总体架构

SectorBreaker 的核心是一个 **ReAct 循环**（Reason → Act → Observe），由 LLM 自主决定下一步做什么，代码只负责执行和记录。

```
┌─────────────────────────────────────────────────────┐
│                    Pipeline 入口                      │
│  run_v2_agent_kernel_pipeline()                      │
│  · 初始化 State / 恢复 checkpoint                     │
│  · 注册工具、创建 Runtime                              │
└─────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────┐
│              AgentKernelRuntime.run()                 │
│                                                      │
│  for iteration in 1..max_iterations:                 │
│    ┌──────────────────────────────────┐              │
│    │ 1. DECIDE  — LLMAgentPolicy      │              │
│    │    读 State + Trace → 输出 JSON   │              │
│    │    AgentDecision {               │              │
│    │      thought_summary,            │              │
│    │      user_notice, ← 面向用户     │              │
│    │      action_type, tool_call,     │              │
│    │      current_goal, plan_steps    │              │
│    │    }                             │              │
│    └──────────┬───────────────────────┘              │
│               ▼                                      │
│    ┌──────────────────────────────────┐              │
│    │ 2. ACT — ToolRegistry.dispatch   │              │
│    │    根据 tool_call.tool_name       │              │
│    │    执行对应 handler               │              │
│    │    → 返回 KernelObservation       │              │
│    └──────────┬───────────────────────┘              │
│               ▼                                      │
│    ┌──────────────────────────────────┐              │
│    │ 3. OBSERVE — reducer.apply_state │              │
│    │    Observation 带回 state_delta   │              │
│    │    reducer 合并到 SectorBreakerState │           │
│    │    去重、治理、记录 decision_log   │              │
│    └──────────┬───────────────────────┘              │
│               ▼                                      │
│    ┌──────────────────────────────────┐              │
│    │ 4. CHECK — 终止条件              │              │
│    │    · FINISH + 有产物 → COMPLETED  │              │
│    │    · FINISH + 无产物 → BLOCKED    │              │
│    │    · 连续失败 ≥ N → FAILED        │              │
│    │    · 达到 max_iterations → MAX    │              │
│    └──────────────────────────────────┘              │
└─────────────────────────────────────────────────────┘
```

**核心原则：LLM 是大脑，代码是手脚。** 代码不决定"下一步搜什么"或"该不该写文档"，只负责执行工具、更新状态、守住安全边界。

---

## 2. 状态机设计

### 2.1 SectorBreakerState — 认知状态

整个 Agent 的"记忆"集中在一个 Pydantic 模型 `SectorBreakerState` 中：

```
SectorBreakerState
├── meta_context: MetaContext          ← 项目元信息（领域、用户目标、安全策略）
├── knowledge_schema: KnowledgeSchema  ← 知识层级结构（L0-L5）
├── shared_knowledge: SharedKnowledge  ← 共享知识库
│   ├── entities: EntityRecord[]       ← 实体（公司、产品、人物）
│   ├── claims: KnowledgeClaim[]       ← 知识主张（带信任度、验证状态）
│   ├── relationships: RelationshipRecord[] ← 实体间关系
│   ├── open_questions: OpenQuestion[] ← 待解决问题
│   └── source_memories: SourceMemory[] ← 来源记忆（搜索结果的结构化摘要）
├── evidence_refs: string[]            ← 所有引用的 evidence ID 列表
├── working_memory: dict<TaskMemory>   ← 任务级工作记忆（临时，可压缩）
├── decision_log: AgentDecision[]      ← Agent 决策历史
├── current_layer_id                   ← 当前聚焦的知识层
└── current_task_id                    ← 当前任务 ID
```

### 2.2 KnowledgeSchema — 知识层级

知识结构按 **L0-L5 六层认知模型** 组织，每层有独立的覆盖度追踪：

| 层级 | ID | 目标 |
|------|-----|------|
| L0 | `L0_prerequisite_basics` | 前置扫盲（可选） |
| L1 | `L1_what_why` | 本源与需求 — 是什么、为什么存在 |
| L2 | `L2_who` | 角色与玩家 — 谁在用、谁在提供 |
| L3 | `L3_how` | 原理与实操 — 怎么实现、需要什么工具 |
| L4 | `L4_money_incentives` | 商业与激励 — 怎么赚钱、成本在哪 |
| L5 | `L5_risks_boundaries` | 风险与边界 — 政策、技术、伦理 |

每层独立追踪：

```python
class KnowledgeLayer:
    coverage_status: CoverageStatus  # not_started / needs_more / sufficient / blocked
    coverage_score: float            # 0.0 ~ 1.0
    ready_to_write: bool             # 是否可以写文档
    evidence_count: int              # 关联证据数
    claim_count: int                 # 关联主张数
    open_question_count: int         # 未解决问题数
    guiding_questions: list[str]     # 引导问题
    completion_criteria: list[str]   # 完成标准
```

**关键设计：L1-L5 是认知 schema，不是路由表。** Agent 不会机械地按 L1→L2→L3 顺序走，而是根据覆盖度、证据质量和用户目标自主决定先做哪层。

### 2.3 KnowledgeClaim — 知识主张

每条从搜索/文档中提炼的知识都是一个 `KnowledgeClaim`，带完整的信任链：

```python
class KnowledgeClaim:
    text: str                         # 主张内容
    evidence_ids: list[str]           # 支撑证据
    trust_level: TrustLevel           # high / medium / low / unknown
    verification_status: str          # unverified / partially_verified / verified
    superseded_by: str | None         # 被更新的主张取代
    conflicts_with: list[str]         # 与哪些主张冲突
    hidden_from_context: bool         # 是否从上下文中隐藏（治理操作）
```

---

## 3. 状态更新机制

### 3.1 KernelStateDelta — 增量更新

每个工具执行完后返回 `KernelObservation`，其中包含 `KernelStateDelta`：

```
工具执行 → KernelObservation {
    success: bool,
    summary: str,
    state_delta: KernelStateDelta {
        source_memories: [...],       ← 新来源
        claims: [...],                ← 新主张
        updated_claims: [...],        ← 更新已有主张
        entities: [...],              ← 新实体
        open_questions: [...],        ← 新问题
        evidence_ids: [...],          ← 新证据 ID
        coverage_updates: [...],      ← 覆盖度变更
        hidden_source_ids: [...],     ← 治理：隐藏来源
        deleted_claim_ids: [...],     ← 治理：删除主张
        superseded_claim_ids: [...],  ← 治理：标记过时
        resolved_open_question_ids: [...], ← 标记已解决
    }
}
```

### 3.2 Reducer — 状态合并

`reducer.apply_state_delta()` 负责把 delta 合并到 State，核心逻辑：

```
apply_state_delta(state, delta, decision, observation)
│
├── 1. 治理操作（先执行）
│   ├── 删除 source_memories（by deleted_source_ids）
│   ├── 隐藏 source_memories（by hidden_source_ids）
│   ├── 删除 claims（by deleted_claim_ids）
│   ├── 隐藏/标记过时 claims（by hidden/superseded_claim_ids）
│   └── 标记问题已解决（by resolved_open_question_ids）
│
├── 2. 新增数据（去重后追加）
│   ├── source_memories → 按 source_id 去重
│   ├── entities → 按 (name, entity_type) 去重
│   ├── claims → 文本去重 + 语义相似度检测（overlap ≥ 0.62 → 冲突）
│   ├── relationships → 按 (source, target, type) 去重
│   └── open_questions → 按 (question, layer_ids) 去重
│
├── 3. 覆盖度更新
│   └── 逐层更新 coverage_score / status / ready_to_write
│
├── 4. 证据 ID 合并
│   └── evidence_refs += delta.evidence_ids + observation.evidence_ids
│
└── 5. 决策日志
    └── state.decision_log.append(映射后的 StateDecision)
```

**去重策略：**
- 来源/实体/关系/问题：精确匹配（归一化后比较）
- 主张：先精确去重，再 **语义相似度检测**（中文双字切分 + token overlap ≥ 62% 视为重复，≥ 42% 且共享证据视为冲突）

---

## 4. 上下文与记忆管理

### 4.1 两层上下文架构

```
SectorBreakerState（完整状态，持久化到 SQLite）
        │
        ▼
ContextPackBuilder（选择性提取）
        │
        ▼
ContextPack（精简上下文，注入 LLM prompt）
        │
        ▼
KernelContextBuilder（组装最终 prompt）
```

### 4.2 ContextPackBuilder — 智能筛选

`ContextPackBuilder` 不会把整个 State 丢给 LLM，而是按预算精选：

```python
class ContextPackBudget:
    max_entities: int = 10           # 最多 10 个实体
    max_claims: int = 12             # 最多 12 条主张
    max_sources: int = 8             # 最多 8 条来源
    max_open_questions: int = 8      # 最多 8 个问题
    max_chars_per_source: int = 360  # 每条来源最多 360 字符
    max_total_chars: int = 7000      # 总上下文最多 7000 字符
```

**筛选逻辑：**

1. **来源筛选**：按 (use 类型 + trust_level + evidence 关联 + relevance_score + 关键词匹配) 打分排序，取 top-N。过滤掉 REJECTED、噪音（网页噪声词）、重复摘要。

2. **主张筛选**：按 (有 evidence + trust_level + 关键词匹配 + 需要验证) 打分排序，取 top-N。过滤掉 hidden、superseded、inactive。

3. **实体筛选**：按当前 layer_id 过滤关联实体。

4. **预算执行**：如果总字符超 7000，从 evidence_summaries 开始裁剪，再裁 claim_summaries。

### 4.3 KernelContextBuilder — Prompt 组装

最终注入 LLM 的 prompt 由 `KernelContextBuilder` 组装，包含 6 个区块：

```
## Meta Context           ← 项目元信息（JSON）
## Knowledge Schema       ← 所有层的覆盖度状态（JSON 数组）
## Curated ContextPack    ← 精选的实体/主张/来源/问题（文本）
## Artifact Memory        ← 已生成的文档摘要（JSON 数组）
## Available Tools        ← 工具规格（JSON 数组）
## Recent Agent Trace     ← 最近 10 条 trace 事件（JSON 数组）
```

### 4.4 工作记忆（Working Memory）

`working_memory` 是任务级的临时记忆，按 task_id 索引：

```python
class TaskMemory:
    task_id: str
    layer_id: str | None
    objective: str                    # 任务目标
    checklist: list[str]              # 待办清单
    attempts: list[ToolAttempt]       # 工具调用记录
    local_reflections: list[str]      # 阶段反思
    memory_summary: str               # 压缩摘要
```

`compressed_reflection()` 方法把任务记忆压缩成 ≤600 字符的摘要，包含：阶段摘要、最近反思、低价值尝试、有效观察。这个摘要会被注入 ContextPack 的 `working_memory_reflection` 字段。

### 4.5 Artifact Memory

已生成的文档不在 State 里（它们存在文件系统），但在 `KernelRuntimeContext.artifacts` 列表中追踪。每次 LLM 决策时，`KernelContextBuilder` 会把 artifact 摘要（ID、标题、路径、字数、引用证据）注入 prompt，让 Agent 知道"已经写了什么"。

---

## 5. Agent 设计

### 5.1 LLMAgentPolicy — 决策器

`LLMAgentPolicy` 是 Agent 的"大脑"，职责：

1. **组装 prompt**：调用 `KernelContextBuilder` 构建上下文，拼接 5 个 prompt 文件（master_agent_system.md、state_reader.md、tool_decision.md、search_strategy.md、coverage_judge.md）。

2. **调用 LLM**：使用 `llm_provider.complete_structured()` 要求 LLM 输出符合 `AgentDecision` schema 的 JSON。

3. **错误修复**：如果 LLM 输出的 JSON 不合法，自动发起一次修复请求（`_repair_decision_json`），把错误信息反馈给 LLM 让它重新输出。

4. **降级兜底**：如果修复也失败，构造一个 `update_task_state` 工具调用来记录错误，保持循环可观察。

### 5.2 AgentDecision — 决策输出

每轮 LLM 输出一个 `AgentDecision`：

```python
class AgentDecision:
    thought_summary: str       # 给技术人看的推理摘要
    user_notice: str = ""      # 给普通用户看的一句话（"我在查商业模式"）
    action_type: AgentActionType  # call_tool / write_artifact / finish / block / ...
    tool_call: ToolCall | None    # 单个工具调用
    tool_calls: list[ToolCall]    # 多个顺序工具调用
    current_goal: str             # 当前阶段目标
    plan_steps: list[str]         # 短期计划
    progress_check: str           # State 离目标还差什么
    stop_reason: str              # finish/block 时的原因
```

**`user_notice` 的设计哲学：** Agent 在决策时就知道"我为什么这么做"。让 LLM 在同一次调用里生成面向用户的自然语言通知（"我先去查一下这个行业有哪些玩家"），而不是代码事后用 `if tool_name == ...` 硬编码翻译。

### 5.3 工具体系

工具按职责分为 6 组：

| 分组 | 工具 | 职责 |
|------|------|------|
| **搜索** | `search_web`, `inspect_evidence` | 从外部获取证据 |
| **文档** | `read_uploaded_report`, `retrieve_project_memory` | 读取用户上传材料和项目记忆 |
| **状态** | `evaluate_coverage`, `internalize_observation`, `manage_state_memory`, `reflect_on_progress`, `update_task_state` | 评估覆盖度、内化观察、治理记忆 |
| **写作** | `write_layer_document`, `write_explainer_card`, `write_explainer_cards_batch`, `write_vault_index`, `review_artifact`, `revise_layer_document`, `finish_run` | 生成/审查/修订文档 |
| **叙事** | `generate_run_narrative` | 生成第一人称调研复盘 |
| **交互** | `ask_user` | 人类介入 |

**写作工具的防假产物机制：**
- `write_layer_document` 使用分段写作（先尝试完整文档，失败后按 5 节分写），每节要求 ≥180 字符
- `_usable_markdown()` 校验：总长度 ≥600 且至少 1 个二级标题
- `_usable_card_markdown()` 校验：总长度 ≥500、有 frontmatter、至少 2 个二级标题
- 只有通过校验的内容才会 append 到 `context.artifacts`

### 5.4 失败恢复机制（V3）

**卡片失败不杀 run：**
- 辅助写入器（`write_explainer_card`、`write_vault_index`、`generate_run_narrative`）失败 → severity="warning"，记录后继续
- 主写入器（`write_layer_document`、`revise_layer_document`）失败 → severity="error"，记录后继续
- 连续失败 ≥ `max_consecutive_failed_tools`（默认 3）→ 停止

**已写成产物不丢失：**
- `pipeline.py` 在判断 run 状态之前，先把所有 `runtime_context.artifacts` 持久化到数据库
- 有真实产物 + 有失败 → `partial_success=True`，以 warning 通知用户
- 完全没有产物才算真正失败

**Checkpoint 恢复：**
- 每次成功写入 artifact 后自动保存 State checkpoint 到 SQLite
- run 结束后保存最终 checkpoint
- `/continue` API 可从 checkpoint 恢复 State，继续未完成的 run

### 5.5 运行时配置

`KernelLoopConfig` 控制循环的"预算"：

```python
class KernelLoopConfig:
    max_iterations: int = 36           # 最大迭代轮数
    max_search_calls: int = 16         # 最大搜索次数
    max_writer_calls: int = 16         # 最大写作次数
    max_consecutive_failed_tools: int = 3  # 连续失败上限
```

根据项目深度自动调整：
- `deep` → 56 iterations / 24 searches / 28 writes
- `standard` → 44 / 20 / 22
- `quick` → 36 / 16 / 16

可通过环境变量 `SECTORBREAKER_KERNEL_*` 覆盖。

---

## 6. 数据流全景

```
用户输入（领域 + 目标）
        │
        ▼
Pipeline 初始化
├── build_adaptive_schema() → KnowledgeSchema（L0-L5 层级）
├── SectorBreakerState.initialize() → 初始状态
├── _internalize_uploaded_documents() → 上传文档写入 State
└── build_default_tool_registry() → 注册所有工具
        │
        ▼
ReAct 循环（最多 N 轮）
├── LLMAgentPolicy.decide()
│   ├── KernelContextBuilder.build_prompt_context()
│   │   ├── ContextPackBuilder.build() → 精选上下文
│   │   └── 拼接 Meta + Schema + Pack + Artifacts + Tools + Trace
│   ├── LLM.complete_structured() → AgentDecision JSON
│   └── 错误修复 / 降级兜底
│
├── ToolRegistry.dispatch()
│   └── 执行对应 handler → KernelObservation
│
├── apply_state_delta()
│   ├── 治理操作（删除/隐藏/标记过时）
│   ├── 去重追加（来源/实体/主张/关系/问题）
│   ├── 覆盖度更新
│   └── 决策日志
│
└── 终止检查
    ├── COMPLETED（FINISH + 有产物）
    ├── BLOCKED（FINISH + 无产物 / LLM 未配置）
    ├── FAILED（连续失败过多 / 写作全部失败）
    └── MAX_ITERATIONS（达到预算上限）
        │
        ▼
产物持久化
├── 所有 artifacts → SQLite
├── State checkpoint → SQLite
└── 导出目录 → Obsidian Markdown（docs/ + cards/）
```

---

## 7. 关键设计决策

| 决策 | 理由 |
|------|------|
| LLM 自主决策，不做硬编码 workflow | 领域多样性要求灵活应对，固定流程无法覆盖所有场景 |
| State 是唯一真相源 | 所有跨工具的数据交换通过 State，不用 prose 传递关键信息 |
| ContextPack 有预算上限 | 防止上下文膨胀导致 LLM 注意力稀释 |
| 主张去重用语义相似度 | 精确匹配会漏掉"同义不同表述"的重复主张 |
| 写作工具只存通过校验的内容 | "防假产物"铁律：不存模板空壳 |
| 卡片失败不杀整轮 run | 辅助文档失败不应导致已写成的主文档丢失 |
| user_notice 由 LLM 实时生成 | 覆盖任意工具（包括未来新增的），零硬编码枚举 |
| checkpoint 持久化到 SQLite | 支持断点恢复，不浪费已完成的工作 |
