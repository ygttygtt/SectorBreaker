# State、Memory、Checkpoint 与恢复

## 为什么 Agent 不能只靠对话历史

纯对话历史存在三个问题：

- Token 无限增长，重要信息会被噪声淹没；
- 结构化事实、证据、开放问题和权限策略难以稳定更新；
- 服务中断后很难精确恢复预算、Artifact 和运行阶段。

SectorBreaker 把“对话”降为输入的一种，把 Agent 认知保存在 Pydantic State 中。

## SectorBreakerState 的主要组成

### MetaContext

保存 Project ID、领域、市场范围、Source Policy、Source Pack、Allow/Block Domain、用户目标、成功标准和安全策略。

MetaContext 中的来源偏好属于可信控制面输入，LLM 可以缩小搜索域，但不能扩张 `require` 的硬白名单。

### KnowledgeSchema

保存每个知识层的：Goal、Priority、Guiding Questions、Completion Criteria、Required Evidence、Coverage Status、Coverage Score、Open Question Count 和 Ready to Write。

### SharedKnowledge

包含：

- EntityRecord；
- KnowledgeClaim；
- RelationshipRecord；
- OpenQuestion；
- SourceMemory。

Claim 还带 Confidence、Trust Level、Verification Status、Evidence IDs、Conflicts、Supersedes、Active 和 Hidden 状态。

### WorkingMemory

`TaskMemory` 用于当前局部任务：Objective、Checklist、ToolAttempt、Local Reflection、Memory Summary 和 Stop Reason。

它与 SharedKnowledge 的区别：WorkingMemory 可以保存失败查询和阶段反思，不应该把每次尝试都污染长期知识。

### ArtifactMemory

记录 Artifact ID、路径、标题、Revision、Content Hash、Active、Supersession、Review Status、Known Gaps 和 Last Modified Run ID。

Agent 每轮决策能看到已有文档摘要，避免重复写同一主题，也能对指定 Active Artifact 发起修订。

### Knowledge Control Plane State

还包括 Vault Import ID、Health Report ID、Maintenance Task IDs、Active Objective、Delegation Log 和 Human Feedback。

### AutonomyPolicy 与 RunBudgetUsage

AutonomyPolicy 保存执行模式、是否允许联网、Create/Update/Move/Delete 权限、Evidence 要求、写入路径和硬预算。

RunBudgetUsage 保存已经消耗的 Search Calls、Provider Requests、Extraction Requests 和 Writer Calls。

## ContextPack 过滤策略

Agent 不读取整个 State JSON，而是由 ContextPackBuilder 挑选：

- 当前目标和知识层；
- 相关 Entity/Claim/Evidence；
- 未解决问题；
- TaskMemory 压缩反思；
- Included/Excluded Source IDs；
- Filter Notes。

默认排除 Hidden、Rejected、Superseded 和无关内容。这样能控制 Token，也能防止旧 Claim 重新污染决策。

## StateDelta 如何合并

工具不能任意修改 State，而是返回 `KernelStateDelta`。Reducer 执行统一治理：

- SourceMemory 按 Source ID 去重；
- Entity 按标准化名称和类型去重；
- Claim 按文本和语义 Token 检查重复/冲突；
- Verified Claim 检查 Evidence 是否属于当前 Project；
- Open Question 去重并挂到对应 Knowledge Layer；
- 更新 Coverage；
- Hide/Delete/Supersede/Resolve Memory；
- 记录决策和阶段反思。

这比让每个 Tool Handler 直接修改任意字段更容易测试和审计。

## Claim 降级机制

如果 LLM 返回 `verification_status=verified`：

- 没有任何当前 Project Evidence：降为 `unverified`；
- 只有部分 Evidence ID 存在：保留真实 ID，降为 `partially_verified`；
- 全部 ID 存在：通过 ID 存在性门禁。

注意：当前只证明 Evidence ID 存在并归属正确，还没有完全实现 Claim 文本与 Evidence 正文之间的语义蕴含校验。这是后续 Claim-level Support Gate 的重点。

## Coverage Score 的当前计算

`evaluate_coverage` 不是让 LLM 凭感觉返回一个数字，而是根据当前层的 State 计算：

```text
score = evidence_score * 0.35
      + claim_score * 0.30
      + verification_score * 0.25
      + source_score * 0.10
      - open_question_penalty
```

- Evidence 数按 Completion Criteria 的约两倍归一化；
- Claim 数按 Completion Criteria 数量归一化；
- Verification Score 是 Verified/Partially Verified Claim 占比；
- Source Score 最多按 4 个 Active Source Memory 归一化；
- 每个未解决问题产生惩罚，总惩罚最高 0.35。

通常 Score >= 0.72 且未解决问题不超过 1 个为 Sufficient；Score >= 0.48 或满足 Partial Material 条件时为 Degraded；否则 Needs More。Degraded 仍可写初版，但必须保留待验证项。

## Checkpoint 类型

### 可恢复 Checkpoint

- `artifact_write`：Artifact 已持久化，State 与其一致。
- `run_end_completed`：Run 已完成且有持久 Active Artifact。

### 诊断/部分成功 Checkpoint

- `run_end_partial`：有部分产物，但 Run 没达到完成条件。
- `run_end`：失败或 Block 的诊断 State。

普通 Project Continue 只加载明确可恢复的 `artifact_write` 或 `run_end_completed`，避免把失败半状态当成成功上下文。

## 为什么 Artifact 必须先于 Checkpoint 写入

错误顺序：

```text
save checkpoint referencing ART-123
  -> process crashes
  -> ART-123 never persisted
```

正确顺序：

```text
persist Artifact revision
  -> sync ArtifactMemory
  -> persist checkpoint referencing Artifact
```

Pipeline 在每次成功写作后执行这个顺序，Run 结束时再做一次幂等持久化兜底。持久化失败会向 API 边界传播，不允许报告 Completed。

## Human-in-the-loop Resume

当 Agent 调用 `ask_user` 或工具返回 `requires_human=True` 时：

1. Run 状态变为 `waiting_for_human`；
2. 保存 Durable Checkpoint；
3. 前端展示 Resume 操作；
4. `/api/runs/{run_id}/resume` 使用 Compare-and-Set 原子认领同一个 Run；
5. Guidance、Evidence Data 和 Assistant Brief 写入持久层；
6. Feedback 注入 `state.human_feedback`；
7. Assistant Brief 作为低可信 Project Document 内化；
8. 使用同 Run ID 和原预算继续 Master 决策。

为什么同 Run 预算不重置：否则 Agent 可以通过反复请求人工确认绕过 Search/Writer 限额。

## Crash Recovery 与 Resume 的区别

- Resume：人为等待后的正常继续，保持同一个 Run ID。
- Recover：Worker 崩溃或 Lease 过期后的恢复，为原 Run 创建一个唯一恢复子 Run，并通过 `resumed_from_run_id` 保留血缘。

如果 Lease 过期：

- 有 Checkpoint：Run -> `interrupted`，允许 Recover；
- 无 Checkpoint：Run -> `failed/orphaned_no_checkpoint`，不伪装成可恢复。

## Lease 机制

Run Worker 拥有 `lease_owner_id` 和 `lease_expires_at`。追加 Event 或 Finalize 时，SQL 会校验：

- Run 当前是 Running；
- Owner ID 匹配；
- Lease 未过期。

旧 Worker 失去 Lease 后不能继续追加事件或把 Run 标 Completed，避免双 Worker 并发写导致状态分叉。

## 面试回答：怎么恢复一个中断 Agent

> 我们不是恢复 Python 调用栈，而是恢复可持久化的业务 State。每次 Artifact 写入后会先持久化不可变 Revision，再保存完整 Pydantic State Checkpoint。人工等待用同 Run Resume，并恢复历史预算；Worker 崩溃则通过 Lease Reconciliation 把有 Checkpoint 的 Run 标记为 Interrupted，再创建唯一的血缘子 Run。恢复后重新构建 ContextPack 和 Active Artifact Memory，由 Master Agent 从当前 State 继续决策。
