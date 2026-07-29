# Agent Kernel 与 Multi-Agent 协作

## 为什么要自研 Agent Kernel

项目早期曾经出现过“代码里有 Master Agent、ReAct、L1-L5，但真实执行仍是固定阶段链”的问题。固定链会造成：

- 每个领域都按同一顺序机械研究；
- 证据不足时仍然自动进入写作；
- 上传资料对后续决策影响不明显；
- UI 图比后端真实执行更丰富；
- 测试验证了节点运行，却没有验证最终知识是否可用。

因此当前架构把执行中心收敛到一个有界 Agent Loop，而不是继续给旧 Workflow 打补丁。

## ReAct 循环的真实实现

核心循环位于 `AgentKernelRuntime.run()`：

```text
build context
  -> LLM returns AgentDecision
  -> validate action/tool payload
  -> dispatch approved tool
  -> receive KernelObservation
  -> apply KernelStateDelta
  -> emit Trace/SSE event
  -> decide again
```

终止条件包括：

- `finish`：完成且本轮有真实产物；
- `ask_user` 或 Observation.requires_human：进入 waiting_for_human；
- `block`：缺少权限、证据或安全路径；
- 连续工具失败达到上限；
- 达到 Max Iterations；
- 关键持久化异常向上抛出。

### 默认运行强度

Pipeline 会根据 Project Depth 选择默认上限，再与 AutonomyPolicy 取更小值：

| 深度 | Max Iterations | Search Calls | Provider Requests | Extraction Requests | Writer Calls |
| --- | ---: | ---: | ---: | ---: | ---: |
| Quick | 36 | 16 | 32 | 12 | 16 |
| Standard | 44 | 20 | 48 | 20 | 22 |
| Deep | 56 | 24 | 64 | 24 | 28 |

这些是运行强度和成本上限，不是“搜到第 N 次就一定足够”的质量判断。还可以通过 `SECTORBREAKER_KERNEL_MAX_*` 环境变量覆盖。

## AgentDecision 为什么要强类型

`AgentDecision` 使用 Pydantic 校验：

- 需要工具的 Action 必须携带 `tool_call` 或 `tool_calls`；
- Finish/Block 必须有 `stop_reason`；
- 工具参数由 Tool Spec JSON Schema 描述；
- Structured Output 失败后允许一次 JSON Repair；
- Repair 仍失败时不会切换为固定流程，而是记录错误并继续受控自修正。

这解决了 LLM 常见问题：字段缺失、工具名幻觉、输出 Markdown Code Fence、JSON 前后夹杂解释等。

## Tool Registry

当前 Master Agent 可见工具大致分为八类。

### 搜索和资料

- `search_web`
- `read_uploaded_report`
- `retrieve_project_memory`
- `inspect_evidence`

### State 和反思

- `internalize_observation`
- `update_task_state`
- `evaluate_coverage`
- `reflect_on_progress`
- `manage_state_memory`

### 知识库控制面

- `inspect_vault_health`
- `inspect_maintenance_backlog`
- `propose_change_set`

### Multi-Agent

- `delegate_specialists`

### Artifact

- `write_layer_document`
- `write_explainer_card`
- `write_explainer_cards_batch`
- `write_vault_index`
- `review_artifact`
- `revise_layer_document`
- `finish_run`

### 人工介入和叙事

- `ask_user`
- `generate_run_narrative`

Tool Registry 对未知工具返回结构化失败 Observation，而不是让 Python 直接异常退出。

## 一次决策为什么可以返回多个 Tool Call

`AgentDecision` 同时支持单个 `tool_call` 和有序 `tool_calls`。适合表达紧密依赖的短动作，例如：

```text
evaluate_coverage
  -> 根据新的 Coverage State
  -> search_web 或 write_layer_document
```

Runtime 仍然逐个执行，每个 Observation 都先进入 Reducer，再执行下一个 Tool Call，因此不是把多个工具黑盒批处理。

## 四类 Specialist Agent

### Vault Auditor

目标：解释确定性审计结果、识别需要语义判断的知识问题。

允许：查看 Health、Backlog、项目检索。

禁止：伪造断链等确定性结果、直接修改文件。

### Researcher

目标：围绕维护目标和知识缺口整理本地资料、研究问题和外部搜索建议。

允许：项目检索、建议 `search_web`。

禁止：升级弱来源为 Verified、直接写知识文件。

### Verifier

目标：检查 Claim、证据、反证、来源质量和冲突。

允许：项目检索、建议验证性搜索。

禁止：没有证据就把 Claim 标记 Verified、删除冲突历史。

### Knowledge Editor

目标：根据 Active Artifact 和 Verified State 形成完整修改建议。

允许：项目检索、返回 `proposed_change` 或建议 `propose_change_set`。

禁止：直接 Apply、直接写文件、Move/Delete、引入无证据事实。

## Specialist 如何并发

Master 可以一次委派最多四个独立任务。实现中通过 `asyncio.gather(..., return_exceptions=True)` 并发调用。某个 Specialist 失败不会自动取消全部任务，最终 Observation 会分别记录 Completed Results 和 Failures。

并发的适用场景：

- Researcher 分别研究两个独立概念；
- Verifier 检查不同 Claim；
- Auditor 和 Researcher 分别处理结构缺口与事实缺口。

不适合并发：后一个任务依赖前一个任务刚生成的 Evidence 或 ChangeSet。

## Multi-Agent 的安全边界

每个 Specialist Result 会经过 Role Boundary 校验：

- 角色只能推荐白名单工具；
- 非 Knowledge Editor 不能返回 Proposed Change；
- Specialist 不能推荐 Apply ChangeSet；
- 所有外部工具调用最终仍由 Master 的 Runtime Budget 和 Provider Boundary 控制。

这样做的目的不是限制智能，而是避免“每个 Agent 都能随意联网和写数据库”导致权限扩散、预算失控和不可追踪副作用。

## 当前 Multi-Agent 的真实成熟度

可以说：

> 当前已经实现 Master 动态委派、四类 Typed Specialist、角色工具白名单、最多四任务并发、结构化 Finding 和 Delegation Log。

不能说：

> 每个 Specialist 都是拥有独立长期记忆和多轮工具循环的完整 ReAct Agent。

下一阶段才会做 Per-Specialist Budgeted Dispatcher、独立 Observation Loop、Finding 自动提升为 StateDelta/ChangeSet，以及 Delegation Quality Metrics。

## Agent 可控性如何保证

控制分四层：

1. Schema：Pydantic Decision、Observation、StateDelta、SpecialistResult。
2. Capability：Tool Registry 和 Role Allowlist。
3. Policy：AutonomyPolicy、Source Policy、路径限制、Evidence Gate。
4. Runtime：搜索、Provider、Extraction、Writer、文件数、字节数、连续失败和迭代上限。

默认 AutonomyPolicy 还限制单 Run 最多 8 个文件、约 200,000 Changed Bytes，只允许 `docs/`、`cards/`、`followups/` 等安全前缀；Create 默认允许，Existing Update 默认要求提案，Move/Delete 默认拒绝。

因此 LLM 决定“想做什么”，代码决定“能不能做、花多少预算、结果如何持久化”。

## 面试示例：研究“API 中转站”

1. Master 看到 L3 技术原理覆盖不足，调用 `search_web` 搜索实现机制。
2. Observation 返回网关、反向代理、Key Pool 等线索和 Evidence。
3. Reducer 将 Claim、SourceMemory、Open Question 加入 State。
4. Master 发现“反向代理”是新手障碍，委派 Researcher 收集解释要点，并创建 Drill-down Question。
5. Master 调用 `evaluate_coverage`，发现主文档可写但仍有部分待验证项。
6. 写 L3 主文档，同时把未验证内容显式保留为风险或后续任务。
7. 调用 `write_explainer_card` 生成“反向代理”概念卡。
8. 调用 `review_artifact` 检查长度、结构和 Evidence ID 是否真实存在。
9. 生成导航页并 Finish。

这里没有代码规定必须先 L1、再 L2、再 L3；顺序来自当时 State 中的知识缺口。
