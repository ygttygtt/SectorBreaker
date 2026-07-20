# SectorBreaker Agent Kernel 面试讲解手册

> 目标：帮助项目作者真正理解 SectorBreaker 当前生产路径，并能在面试中用代码、数据结构和运行链路证明它为什么是 Agent，而不是只会复述“感知—思考—行动”。

## 1. 先理解那份 65 分评价

模拟面试给出的批评可以分成两类。

第一类是“项目没有讲出来”，不等于“项目没有实现”：

- 没有讲清 Tool Call 的结构和分发过程；
- 没有展开 ReAct 每一轮如何运行；
- 没有解释 State、Observation、StateDelta 和 Reducer；
- 没有给出搜索失败、写作失败、无产物结束等异常路径；
- 没有用覆盖率、证据状态和终止条件回答“不确定性判断”。

第二类是当前项目确实还不完整：

- 当前个人知识库生产路径是单 Master Agent，不是成熟的多 Agent 协作系统；
- `TaskMemory` 和 Reflection 模型已经存在，但生产 Pipeline 尚未自动为每个研究任务建立完整的工作记忆和 ToolAttempt；
- `max_search_calls`、`max_writer_calls` 当前主要作为给 LLM 的软强度提示，运行时 `_budget_check()` 还没有真正执行硬限制；
- claim 冲突处理目前更接近“相似项去重和冲突标记”，还不是严谨的事实矛盾识别与裁决系统；
- `evaluate_coverage` 有量化公式，但它仍是启发式指标，不是经过标注数据验证的研究质量评分器。

因此，最稳妥的面试策略不是反驳面试官，而是：

> 用真实代码链路证明项目已经是 Agent Kernel，同时主动说明哪些能力是第一版、哪些仍在演进。能说清边界，比把所有能力都说成“已经完整实现”更像成熟工程师。

---

## 2. 一句话定义这个项目

SectorBreaker 是一个面向陌生领域研究的、以 Obsidian 知识库为产物的有状态 Agent。

它的核心不是“调用一次大模型生成报告”，而是：

```text
读取当前 State
  → LLM 选择下一行动和工具
  → Tool Registry 执行真实工具
  → Observation 返回结构化 StateDelta
  → Reducer 更新 State
  → LLM 根据新 State 再决策
  → 直到写作、审查、询问用户、阻断或结束
```

最重要的代码入口是：

- `backend/app/agent_kernel/pipeline.py`
- `backend/app/agent_kernel/runtime.py`
- `backend/app/agent_kernel/policy.py`
- `backend/app/agent_kernel/tool_registry.py`
- `backend/app/agent_kernel/reducer.py`

---

## 3. 为什么它不是固定工作流

### 3.1 判断标准不是“有没有 LangGraph”

使用 LangGraph 不等于使用 Agent；没有把所有逻辑写成图，也不等于不是 Agent。

判断一个系统是不是 Agent，要看：

1. 是否有持续存在的状态；
2. 下一步行动是否由模型根据状态动态决定；
3. 是否能从多个真实工具中选择；
4. 工具结果是否会反馈到下一轮决策；
5. 是否存在动态继续、改搜、写作、询问、阻断和结束；
6. 是否有工程边界约束模型行为。

SectorBreaker 当前生产路径满足这套基本条件。

### 3.2 固定工作流与当前实现的区别

固定工作流通常是：

```python
search_definition()
search_players()
search_technology()
search_business()
search_risks()
write_report()
```

无论资料情况如何，下一节点都由代码提前确定。

SectorBreaker 当前的 Runtime 是：

```python
for iteration in range(...):
    decision = await policy.decide(state, tools, trace, artifacts)
    observation = await registry.dispatch(decision.tool_call, context)
    context.state = apply_state_delta(state, observation.state_delta, ...)
```

也就是说，代码固定的是“决策—执行—观察—更新”的控制循环，不固定具体研究步骤。

如果上传报告已经覆盖了玩家，Agent 可以不再搜索玩家；如果搜索技术原理时发现“反向代理”，Agent 可以创建下钻任务；如果证据不足，它可以再次搜索；如果目标不明确，它可以调用 `ask_user`。

### 3.3 L1-L5 不是流程节点

项目将领域知识组织为：

- L0：前置扫盲；
- L1：本源与需求；
- L2：角色与玩家；
- L3：原理与实操；
- L4：商业与激励；
- L5：风险与边界。

它们是 Knowledge Schema 和 Coverage Rubric，用于描述“一个可用知识库应该覆盖什么”，不是规定执行顺序。

面试中可以说：

> 我保留了稳定的认知框架，但没有把框架写成固定控制流。稳定的是质量标准，动态的是下一步行动。

---

## 4. 一轮 ReAct 到底怎么执行

### 4.1 Decide：构建上下文并让 LLM 决策

`KernelContextBuilder` 给 LLM 的不是整个数据库，而是六类精选信息：

1. Meta Context：领域、用户目标、市场范围、来源策略；
2. Knowledge Schema：每个知识层的目标和覆盖状态；
3. ContextPack：筛选后的实体、主张、证据、开放问题；
4. Artifact Memory：已经写出的文档摘要；
5. Available Tools：当前允许调用的工具 Schema；
6. Recent Trace：最近的 Thought、Action、Observation、State Update。

LLM 通过 `complete_structured()` 输出 `AgentDecision`：

```json
{
  "thought_summary": "现有资料解释了定义，但没有说明技术机制。",
  "user_notice": "我再查一下它具体是怎么工作的。",
  "action_type": "call_tool",
  "current_goal": "补足 API 中转站的转发和协议转换机制",
  "plan_steps": ["搜索实现机制", "整理关键术语", "重新评估覆盖"],
  "progress_check": "已有定义和玩家信息，缺少技术链路",
  "tool_call": {
    "tool_name": "search_web",
    "args": {
      "query": "API 中转站 原理",
      "queries": [
        "API 中转站 原理",
        "模型网关 协议转换",
        "AI API relay protocol conversion"
      ],
      "layer_hint": "L3_how",
      "search_goal": "查找请求转发、鉴权、协议转换和关键术语",
      "max_results": 8
    },
    "reason": "当前技术层的关键问题尚未覆盖"
  },
  "expected_observation": "获得技术机制相关候选证据"
}
```

这里的 Tool Call 是项目定义的结构化 Tool Call，由 Pydantic Schema 验证，再交给 Tool Registry 分发。它不依赖某一家模型厂商的原生 Function Calling，因此兼容 OpenAI-compatible 模型，但也要自己负责 Schema 校验、修复和分发。

### 4.2 Act：Tool Registry 分发真实工具

`ToolRegistry` 保存：

```text
tool_name → ToolSpec + async handler
```

它只允许调用注册过的工具。未知工具不会被执行，而会返回失败 Observation 和可用工具列表。

这解决了两个问题：

- 模型不能声称调用一个并不存在的能力；
- Agent 决策与 Tavily、SQLite、文件系统等基础设施解耦。

### 4.3 Observe：工具返回结构化结果

工具不是只返回一段自然语言，而是返回 `KernelObservation`：

```python
class KernelObservation:
    tool_name: str
    success: bool
    summary: str
    data: dict
    state_delta: KernelStateDelta
    evidence_ids: list[str]
    artifact_ids: list[str]
    requires_human: bool
    error: str | None
```

例如 `search_web` 会返回：

- 原始结果数；
- 去重后采纳数；
- 被过滤结果数；
- 代表性来源标题；
- 新 Evidence ID；
- 新 SourceMemory；
- 默认处于 unverified 状态的 KnowledgeClaim。

### 4.4 Update：Reducer 合并 StateDelta

Reducer 是模型和 State 之间的隔离层。它负责：

- 来源、实体、主张、关系、问题去重；
- 拒绝没有 Evidence 的 verified claim；
- 隐藏、删除或 supersede 旧记忆；
- 更新 coverage score/status；
- 合并 evidence refs；
- 记录可审计的 decision log。

因此，工具返回的 Raw Observation 不会直接污染长期知识状态。

### 4.5 再决策，而不是自动进入下一个固定节点

State 更新之后，Runtime 回到 `policy.decide()`。下一步可能是：

- 再次 `search_web`；
- `read_uploaded_report`；
- `retrieve_project_memory`；
- `inspect_evidence`；
- `internalize_observation`；
- `evaluate_coverage`；
- `reflect_on_progress`；
- `write_layer_document`；
- `write_explainer_card`；
- `review_artifact`；
- `ask_user`；
- `finish` 或 `block`。

这才是项目最应该在面试里讲出来的“动态性”。

---

## 5. Agent 是怎么选择工具的

### 5.1 不是关键词到工具名的硬编码

Agent 主要根据下面五类信息选工具：

| 判断维度 | 例子 | 候选行动 |
|---|---|---|
| 已有材料 | 存在未读 DeepSearch 报告 | `read_uploaded_report` |
| 当前缺口 | 缺少商业模式和定价 | `search_web` |
| 证据问题 | 关键 claim 只有搜索摘要支持 | `inspect_evidence` |
| 研究状态 | 连续搜索重复、价值低 | `reflect_on_progress` |
| 产物状态 | 主文档已写但术语难懂 | `write_explainer_card` |

### 5.2 “搜索核心黑话”和“下一轮搜索”的真实区别

这两者通常不是两个搜索工具。

第一次搜索发现“反向代理”后，Agent 可以先调用 `internalize_observation`，将其写成：

- OpenQuestion；
- drill_down_task；
- coverage gap；
- concept_or_entity。

下一轮如果判断它影响用户理解，再调用同一个 `search_web`：

```json
{
  "query": "反向代理 API 中转站 原理",
  "queries": [
    "反向代理是什么",
    "反向代理 API 网关 请求转发",
    "API 中转站 协议转换 反向代理"
  ],
  "layer_hint": "L3_how",
  "search_goal": "解释反向代理在 API 中转站中的作用"
}
```

所以：

> “核心黑话”是一个研究意图和下钻任务；`search_web` 是执行搜索的通用能力。差异主要体现在 State 中的缺口、query 和 search_goal，而不是为每一种语义意图创建一个新工具。

### 5.3 为什么不把每种搜索拆成不同工具

如果创建 `search_definition`、`search_jargon`、`search_players`、`search_risk` 等大量工具，会产生：

- 工具数量膨胀；
- 能力边界重叠；
- 模型选择困难；
- 新领域出现新意图时需要修改代码；
- 搜索基础设施和研究方法耦合。

当前设计将它们拆成：

```text
研究意图：由 LLM 根据 State 生成
搜索执行：统一由 search_web 完成
搜索引擎：由 SearchProvider 配置决定
结果治理：由 Evidence + StateDelta + Reducer 完成
```

### 5.4 Agent 不直接选择 Tavily 还是 Serper

Agent 选择“为什么搜、搜什么”，Provider 层决定“通过什么搜索服务执行”。

`SearchProvider` 是统一接口，运行配置可以选择：

- Tavily；
- Serper；
- Brave；
- Exa；
- MultiSearchProvider 聚合。

这是 Strategy 与 Infrastructure 的解耦。

---

## 6. State 和记忆架构怎么讲

### 6.1 当前核心 State

`SectorBreakerState` 包含：

```text
meta_context
knowledge_schema
shared_knowledge
  ├─ entities
  ├─ claims
  ├─ relationships
  ├─ open_questions
  └─ source_memories
evidence_refs
working_memory
decision_log
human_feedback
current_layer_id
current_task_id
```

### 6.2 三层记忆视角

面试时可以把它解释成三层，但要说明实现成熟度。

#### 运行上下文

- 最近 10 条 trace；
- 当前目标、计划和 progress check；
- 当前 Artifact Memory；
- 当前精选 ContextPack。

作用是支撑下一轮即时决策。

#### 结构化研究记忆

- Entity；
- Claim；
- Relationship；
- SourceMemory；
- OpenQuestion；
- Evidence Ref；
- Coverage Status。

这是跨轮次复用的主要“世界模型”。

#### 持久化项目记忆

- SQLite 中的 evidence、documents、segments、artifacts；
- run state checkpoint；
- 导出的 `.sectorbreaker` 状态包；
- 后续问答产生的 follow-up artifact。

它用于断点恢复、项目检索和知识库持续生长。

### 6.3 ContextPack 为什么重要

如果把所有搜索结果、文档和 Trace 全塞给模型，会出现：

- Token 成本持续增加；
- 低质量信息稀释重要证据；
- 已失败 Query 反复出现；
- 旧 Claim 与新 Claim 混在一起；
- 模型难以判断真正缺口。

所以 ContextPack 只挑选与当前目标、当前层和当前任务相关的内容，并过滤 hidden、inactive、superseded 和 rejected memory。

### 6.4 必须主动承认的边界

当前 `TaskMemory` 已经定义了 attempts、local reflections、memory summary，也实现了 `reflect_on_progress`。但生产 Pipeline 尚未自动为每个研究目标建立 TaskMemory，也没有在每次工具调用后完整写入 ToolAttempt。

因此面试中不要说“短期记忆系统已经完整闭环”。更准确的说法是：

> 项目已经有结构化 State、ContextPack、Decision Log、Checkpoint 和项目级持久化；任务级工作记忆模型与 Reflection 工具已经落地，但自动任务创建和每次尝试记录仍是下一步完善项。

---

## 7. 不确定性判断如何工程化

### 7.1 不是一句“我觉得够了”

`evaluate_coverage` 会统计当前知识层的：

- Evidence 数量；
- Claim 数量；
- verified/partially verified Claim 数量；
- Source 数量；
- OpenQuestion 数量；
- Completion Criteria 数量；
- Source Policy。

当前评分大致为：

```text
coverage_score =
    evidence_score × 0.35
  + claim_score × 0.30
  + verification_score × 0.25
  + source_score × 0.10
  - open_question_penalty
```

根据分数和问题数量，得到：

- `sufficient`；
- `degraded`；
- `needs_more`；
- `ready_to_write`。

### 7.2 为什么数字不是唯一判断

一个层有十条营销文章，不一定比两份官方文档更可信。因此项目同时把下面信息交给 LLM：

- 用户目标是否覆盖；
- 来源质量和多样性；
- Claim 是否经过验证；
- 上传报告是否只是低可信线索；
- 是否存在关键 OpenQuestion；
- Artifact 是否足够可读；
- 是否触及安全边界。

量化评分是 Guardrail 和可观察信号，LLM 仍负责最终行动判断。

### 7.3 面试官问“你们怎么评估 Agent 好不好”

可以从四层回答：

| 层次 | 指标 |
|---|---|
| 工具执行 | 成功率、空结果率、重复率、连续失败次数 |
| 研究状态 | coverage score、open questions、verified claim 比例、来源多样性 |
| 产物质量 | 文档长度、结构完整性、Evidence ID、Review 结果、是否出现假模板 |
| 系统运行 | 完成率、partial success、最大迭代终止、checkpoint 恢复成功率 |

然后主动说明：

> 当前这些指标已经有一部分进入运行状态和测试，但还没有形成离线标注集、端到端任务成功率和 LLM-as-judge/人工双评的完整评测平台。这是我认为项目下一阶段最值得补的工程能力。

---

## 8. 异常处理和降级怎么讲

### 8.1 LLM 决策 JSON 不合法

处理路径：

1. `complete_structured()` 解析失败；
2. 发起一次 JSON Repair，请模型只返回合法 `AgentDecision`；
3. Repair 仍失败时，不偷偷切换成固定流程；
4. 构造 `update_task_state`，记录错误并让循环保持可观察。

### 8.2 工具不存在或工具抛异常

Tool Registry 返回失败 Observation：

- `success=false`；
- 错误类型和摘要；
- 未知工具时返回 available tools；
- State 将这次行为记录为 degrade/block 类型决策。

### 8.3 连续失败

Runtime 维护 `consecutive_failed_tools`。默认连续失败达到 3 次就停止，防止 Agent 在同一错误路径无限循环。

### 8.4 写作失败

当前区分：

- 主文档写作失败：错误级别更高，但已完成的真实产物保留；
- 可选解释卡、索引、叙事失败：记录 warning，不一定让整轮失败；
- 没有任何产物时不能假装完成；
- `finish` 时如果 artifact 为空，强制 BLOCKED；
- 有成功文档也有失败写作时，返回 `partial_success`。

### 8.5 长时间等待

LLM 决策和文档写作期间会发送 Heartbeat 事件，让前端知道 Agent 仍在处理，而不是无响应。

### 8.6 Human-in-the-loop

`ask_user` 返回 `requires_human=true`，Runtime 将状态变为 `WAITING_FOR_HUMAN`。适用情况包括：

- 目标或市场范围无法从资料判断；
- 需要用户决定优先级；
- 需要用户提供材料；
- 是否允许以 degraded 结果继续必须由用户决定。

---

## 9. 信息冲突怎么回答才诚实

### 9.1 已实现的部分

- Claim 有 `verification_status`、`trust_level`、`evidence_ids`；
- Claim 可以记录 `conflicts_with`、`superseded_by`、`supersedes`；
- Reducer 会做规范化去重；
- 相似 Claim 会被识别，旧 Claim 可被隐藏或 supersede；
- `manage_state_memory` 可以隐藏来源、删除 Claim、更新 Claim、解决 OpenQuestion；
- 外部 AI 报告默认是低/部分可信线索，不直接当 verified fact。

### 9.2 当前不足

Reducer 当前主要通过文本 token overlap 判断“语义相似”，它不能可靠区分：

```text
市场规模增长 20%
市场规模下降 20%
```

两句话可能高度相似，但事实方向相反。当前逻辑也可能把“相似表述”标记成 conflict，而不是严格识别逻辑矛盾。

### 9.3 下一步合理方案

如果面试官追问，可以提出：

1. 先按 Claim subject/predicate/time/market 拆成结构化槽位；
2. 只有同一 subject、同一口径和时间范围才进入冲突比较；
3. 使用 NLI/LLM 输出 `support | contradict | unrelated`；
4. 根据 Source Quality、时效、原始来源距离计算裁决分；
5. 不直接删除败方 Claim，而是保留冲突及裁决理由；
6. 对高影响冲突生成 VerificationTask，搜索原始来源；
7. 仍无法解决时写入 Artifact 的“证据冲突与待验证项”。

这样的回答既展示现状，也展示系统设计能力。

---

## 10. 它是不是多 Agent 系统

当前个人 `domain_knowledge` 的生产核心应准确描述为：

> 单 Master Agent + 多工具 + 结构化 State + Provider/Repository 服务边界。

项目历史和文档中有 Research Planner、Search Scout、Evidence Curator、QA Critic 等角色设计，也存在 Specialist 相关代码，但当前个人知识库生产路径的唯一 Owner 是 V2 Agent Kernel。

不要为了显得高级而把工具或 Python 模块叫成 Agent。

### 为什么当前没有强行使用多 Agent

多 Agent 适合：

- 子任务可以并行；
- 角色需要不同 Prompt、工具权限或模型；
- 需要独立 Critic 对主 Agent 形成制衡；
- 单 Agent 上下文过大；
- 不同任务需要不同 SLA 或成本模型。

但它也会增加：

- 状态一致性问题；
- 消息协议复杂度；
- 重复搜索和 Token 成本；
- 冲突合并；
- Trace 调试难度；
- 失败恢复难度。

当前先把单 Agent 的 State、Tool、Observation、Reducer 和真实产物闭环做稳，是合理的架构选择。

### 如果演进为多 Agent

建议不是让 Agent 自由聊天，而是：

```text
Master Agent
  ├─ 创建结构化 ResearchTask
  ├─ 分派给有限 Specialist
  ├─ Specialist 返回 TaskResult + Evidence IDs + StateDelta Proposal
  ├─ Master/Reducer 审核合并
  └─ Critic 独立检查覆盖和证据
```

跨 Agent 只能传 Pydantic/JSON Contract，不传不可审计的自由散文。

---

## 11. ReAct、Plan-and-Execute、Reflection 怎么定位

### ReAct：当前核心模式

当前明确实现：

```text
Decision → Tool Call → Observation → State Update → Next Decision
```

### Plan-and-Execute：具备轻量计划字段，不是独立双 Agent 架构

`AgentDecision` 包含：

- `current_goal`；
- `plan_steps`；
- `progress_check`。

它允许 Agent 每轮表达短计划，但当前没有独立 Planner 生成长期计划、Executor 严格逐项执行的完整 Plan-and-Execute 架构。

### Reflection：有显式工具，但生产闭环仍可加强

`reflect_on_progress` 可以记录：

- 阶段反思；
- coverage gaps；
- next steps；
- TaskMemory summary。

Prompt 也要求连续低价值搜索后优先反思。不过自动触发策略、TaskMemory 创建和 ToolAttempt 记录还可以继续完善。

### Tree-of-Thought：当前没有实现，不要声称使用

项目没有维护多条推理树、分支评分和回溯搜索。面试中可以解释为什么当前不需要：领域研究的主要瓶颈是证据获取、状态治理和产物质量，不是对同一纯推理问题做大规模搜索树。

---

## 12. 用一个完整例子讲动态循环

假设用户要研究“API 中转站”。

### 第 1 轮：读取状态

Agent 看到：

- 用户希望构建入门知识库；
- 上传报告已经解释了基本定义；
- 报告中的商业规模没有原始来源；
- L3 原理、L4 商业、L5 风险覆盖不足。

决策：不重复搜索定义，先搜索技术机制。

### 第 2 轮：搜索技术机制

调用：

```text
search_web(
  query="API 中转站 原理",
  queries=[...],
  layer_hint="L3_how",
  search_goal="解释转发、鉴权、协议转换"
)
```

Observation：获得 8 条结果，采纳 5 条，出现“反向代理”“模型网关”“协议转换”。

Reducer：写入 Evidence、SourceMemory 和 unverified Claims。

### 第 3 轮：发现黑话并下钻

调用 `internalize_observation`：

- 创建“反向代理是什么”的 OpenQuestion；
- 创建 drill-down task；
- 记录“协议转换机制仍不清楚”的 coverage gap。

### 第 4 轮：定向搜索概念

再次调用同一个 `search_web`，Query 变为“反向代理 API 网关请求转发”。

这说明“下一轮搜索”不是工作流预设，而是上一轮 Observation 改变 State 后产生的新行动。

### 第 5 轮：覆盖评估

调用 `evaluate_coverage(L3_how)`。

如果结果为 `needs_more`，继续搜索或检查 Evidence；如果为 `degraded/sufficient + ready_to_write`，进入写作。

### 第 6 轮：写主文档

调用 `write_layer_document`，生成“原理与实操”主文档，必须基于 State 中的证据和开放问题。

### 第 7 轮：补解释卡

Agent 从 Artifact Memory 发现主文档提到“反向代理”，新手可能不懂，于是调用 `write_explainer_card` 生成独立 Obsidian 页面。

### 第 8 轮：审稿或结束

调用 `review_artifact`。如果文档过薄或缺 Evidence，返回补搜/修订；如果主文档、关键卡片、导航和待验证任务已经可用，才 `finish`。

---

## 13. 面试话术

### 13.1 30 秒版本

> SectorBreaker 是一个把陌生领域研究结果沉淀为 Obsidian 知识库的有状态 Agent。它不是固定按 L1 到 L5 跑流程，而是每轮把结构化 State、覆盖缺口、已有证据、历史观察和可用工具交给 LLM，由 LLM 输出 Pydantic 约束的 AgentDecision。Runtime 通过 Tool Registry 执行搜索、材料读取、覆盖评估、写作或询问用户，再把 Observation 中的 StateDelta 交给 Reducer 去重、验证和更新，之后进入下一轮决策。代码负责边界和可靠性，LLM 负责下一步研究策略。

### 13.2 两分钟版本

> 这个项目最初也经历过“看起来像 Agent、实际是固定工作流”的问题，所以后来做了 V2 Agent Kernel 重构。现在个人知识库生产路径只有一个 Owner，就是 `run_v2_agent_kernel_pipeline`。
>
> 核心循环是 State + Tools + LLM Policy + Observation + Reducer。每一轮，Context Builder 会从完整 State 中筛选当前目标相关的 Claim、Evidence、OpenQuestion、Coverage、Artifact Memory 和最近 Trace，再附上可用 Tool Schema。LLM 输出结构化 AgentDecision，包括当前目标、短计划、进度判断、工具名、参数、调用原因和预期观察。Tool Registry 只执行注册工具，工具结果必须返回 KernelObservation 和 StateDelta，Reducer 再负责去重、Evidence 约束、记忆治理和 Coverage 更新。
>
> 比如搜索 API 中转站时发现“反向代理”，它不会进入预设的下一节点，而是先把这个词内化成 OpenQuestion 和 Drill-down Task，下一轮再决定用同一个 search_web 做更具体的概念搜索，或者直接检索已有项目记忆。什么时候继续搜索、什么时候写主文档、什么时候补概念卡、什么时候问用户或阻断，都是根据更新后的 State 决定的。
>
> 工程上我还做了 JSON 决策修复、未知工具拒绝、连续失败停止、无产物禁止 finish、写作 partial success、Heartbeat、Checkpoint 恢复和 Evidence 状态管理。当前仍有边界：任务级工作记忆自动化、严格冲突裁决和完整 Agent Eval 体系还需要加强，多 Agent 也不是当前生产核心。

### 13.3 “为什么这是真正 Agent”

> 我不以是否用了某个框架来定义 Agent，而看控制权在哪里。我的代码只固定 ReAct 循环和安全边界，不固定业务步骤；下一行动、查询词、是否下钻、是否补搜、是否写作和何时停止，都由模型根据 State 动态决定。工具结果会形成结构化 Observation 并更新下一轮可见的 State，所以它具备闭环，而不是一次性 Tool Calling。

### 13.4 “LLM 决策会不会不可控”

> LLM 负责策略，但没有直接系统权限。它只能输出 AgentDecision Schema 中允许的 Action，Tool Registry 只执行已注册工具；外部调用必须经过 Provider；工具返回 StateDelta 而不是直接修改任意状态；Reducer 会做 Evidence 约束、去重和记忆治理；Runtime 还有连续失败、最大迭代、无产物禁止完成等 Guardrail。所以这是 LLM-controlled、code-governed，而不是让模型随便执行。

### 13.5 “为什么不用多 Agent”

> 当前问题的核心难点是研究状态、证据治理和知识库产物，不是角色数量。我先用单 Master Agent 做稳 State—Tool—Observation 闭环，避免多 Agent 带来状态一致性、重复搜索、成本和调试复杂度。如果未来某些研究任务需要并行、独立权限或独立 Critic，我会通过结构化 ResearchTask 和 TaskResult 扩展 Specialist，而不是让多个 Agent 自由聊天。

---

## 14. 高频追问与回答要点

### Q1：Tool Call 是模型原生 Function Calling 吗？

不一定。当前主要通过 `complete_structured()` 让模型输出符合 Pydantic 的 `AgentDecision`，再由应用层 Tool Registry 分发。优点是兼容不同 OpenAI-compatible 模型；代价是需要自己处理 JSON Repair、未知工具、参数 Schema 和执行 Trace。

### Q2：为什么允许 `tool_calls` 多工具？这还是 ReAct 吗？

它用于同一阶段目标下少量、顺序、低风险的动作，最多建议 3 个。每个工具执行后都会更新 State，但 LLM 不会在这一组中间重新决策，所以依赖前一个结果的强动态动作更适合拆成下一轮。面试中不要把它描述成并行多 Agent。

### Q3：搜索结果为什么不能直接写进最终文档？

搜索结果通常只是 snippet，默认生成 unknown trust、unverified Claim。它可以作为线索，但关键事实还需要来源检查、更多证据或显式标注待验证，防止把搜索摘要当成确定事实。

### Q4：如何避免重复搜索？

- Prompt 会看到近期 Trace 和已有 State；
- Search Tool 对本轮 URL 去重；
- Repository 已存在 URL 会被过滤；
- SourceMemory 和 Claim 进入 Reducer 后再次去重；
- 连续低价值搜索时可调用 Reflection；
- 当前仍可继续增强 ToolAttempt 的自动记录和 Query 指纹。

### Q5：什么时候停止？

- 主文档达到可读标准；
- 关键解释卡和导航已经补齐；
- 核心缺口已经解决或显式记录为待验证；
- Artifact Review 通过；
- Agent 输出 finish/finish_run；
- Runtime 确认至少存在一个真实 Artifact。

另外，最大迭代和连续失败是硬停止条件。

### Q6：Checkpoint 保存什么？

保存 `SectorBreakerState`，包括 Knowledge Schema、Shared Knowledge、Evidence Refs、Decision Log、Human Feedback 等。成功写入 Artifact 后和 Run 结束时都会保存 Checkpoint，用于后续 Continue 恢复。

### Q7：如何证明上传的外部报告真的被使用了？

Pipeline 会在搜索前内化上传文档，将其中的 Claim、Entity、Citation 和 OpenQuestion 写入 State；ContextPack 和 Writer Context 都能读取它们。验收时还应检查事件流和最终 Artifact 是否引用这些材料，而不能只验证“上传接口成功”。

### Q8：现在的 RAG 是关键词匹配还是真向量检索？

当前是本地 Hybrid RAG：SQLite FTS/词项召回与 FastEmbed 真向量召回并行，使用 `BAAI/bge-small-zh-v1.5`，按 content hash 增量索引 evidence、document segments 和 active artifacts，再用 RRF 融合排名。模型失败时会明确标记 `lexical_degraded`。SQLite 当前保存并线性扫描向量，适合本地中小型 Vault；超大库可在保持 Provider 契约的前提下换成 ANN VectorStore。

### Q9：最大的技术债是什么？

建议答三个：

1. TaskMemory/ToolAttempt 还没有在生产循环完全自动化；
2. Claim Conflict 需要结构化事实槽位和 NLI/LLM 裁决；
3. Eval 需要从单元测试和真实样例验收升级为带标注集的任务成功率、证据正确率和 Artifact 质量评估。

### Q10：你在这个项目中最重要的架构教训是什么？

> 最大教训是不要把固定 Workflow 包装成 Agent。我们曾经保留旧 Pipeline、使用固定阶段和模板兜底，导致测试通过但用户产物不可用。后来通过版本隔离，把生产 Owner 收敛到 Agent Kernel，并规定真实端到端输出、事件 Trace 和导出文档才是验收标准。Agent 项目不能只验证内部节点执行成功，必须验证用户最后拿到的知识是否真实、可读、有证据。

---

## 15. 面试中不要说错的内容

不要说：

- “这是成熟的多 Agent 协作系统。”
- “每个 Specialist 都在生产路径独立决策。”
- “搜索和写作预算已经被 Runtime 严格限制。”
- “项目已经完整解决事实冲突。”
- “我们实现了 Tree-of-Thought。”
- “搜索结果都是可信证据。”
- “Evidence 达到固定数量就一定足够。”
- “只要生成 Markdown 就算运行成功。”

建议说：

- “当前生产核心是单 Master Agent，多 Agent 是可扩展方向。”
- “最大迭代和连续失败是硬限制，搜索/写作 strength 当前主要是软引导。”
- “冲突字段和初版治理已经存在，严格语义矛盾裁决仍需加强。”
- “搜索 snippet 默认是 unverified lead。”
- “Coverage 数量指标是 Guardrail，最终还要结合目标、来源质量、开放问题和 Artifact Review。”
- “真实产物、Evidence 关联和端到端验收比节点通过更重要。”

---

## 16. 建议你的复习顺序

第一遍只掌握五个对象：

```text
SectorBreakerState
AgentDecision
ToolCall
KernelObservation
KernelStateDelta
```

第二遍顺着一次调用读代码：

```text
pipeline.py
  → runtime.py
  → policy.py
  → tool_registry.py
  → tools/search.py 或其他 Tool
  → reducer.py
  → runtime.py 下一轮
```

第三遍准备三个真实故事：

1. 发现黑话后如何下钻；
2. 写作失败后为什么不会生成假产物；
3. 旧 Workflow 泄漏如何推动 V2 版本隔离。

第四遍准备三项不足和改进方案：

1. TaskMemory 自动化；
2. Claim Conflict 裁决；
3. Agent Eval 体系。

当你能不看文档画出下面这条链，并能解释每个对象的输入输出，就已经不只是“会背 Agent 概念”：

```text
State
  → ContextPack
  → AgentDecision
  → ToolRegistry
  → KernelObservation
  → KernelStateDelta
  → Reducer
  → New State
```

---

## 17. 代码索引

| 主题 | 文件 |
|---|---|
| 生产入口与 Checkpoint | `backend/app/agent_kernel/pipeline.py` |
| ReAct Runtime | `backend/app/agent_kernel/runtime.py` |
| LLM 决策策略 | `backend/app/agent_kernel/policy.py` |
| Context 组装 | `backend/app/agent_kernel/context.py` |
| AgentDecision/Observation/Delta | `backend/app/agent_kernel/models.py` |
| State/Claim/Memory 模型 | `backend/app/agent_state/models.py` |
| ContextPack 筛选 | `backend/app/agent_state/context_pack.py` |
| Tool Registry | `backend/app/agent_kernel/tool_registry.py` |
| 搜索工具 | `backend/app/agent_kernel/tools/search.py` |
| 状态与 Coverage 工具 | `backend/app/agent_kernel/tools/state.py` |
| 文档/项目记忆工具 | `backend/app/agent_kernel/tools/documents.py` |
| Artifact 写作工具 | `backend/app/agent_kernel/tools/artifacts.py` |
| Human-in-the-loop | `backend/app/agent_kernel/tools/human.py` |
| State Reducer | `backend/app/agent_kernel/reducer.py` |
| Provider 抽象 | `backend/app/providers/interfaces.py` |
| Search Provider 构建 | `backend/app/providers/factory.py` |
| 架构原则 | `docs/18-agent-kernel-design-philosophy.md` |
| 调试复盘 | `docs/19-agent-kernel-debugging-retrospective.md` |
| 版本隔离 | `docs/20-version-isolation-and-cutover-rules.md` |
| 完整架构说明 | `docs/22-agent-kernel-architecture.md` |
