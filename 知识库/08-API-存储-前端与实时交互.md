# API、存储、前端与实时交互

## API 设计原则

- FastAPI 提供 API；
- Pydantic 是请求和响应契约真相源；
- Unknown Product Mode 被拒绝，不兼容已退休企业模式；
- Agent、Provider 和知识控制面通过接口分离；
- 长任务通过 Run + SSE 观察，不阻塞普通请求。

## 主要 API 分组

### Project

```text
POST  /api/projects
GET   /api/projects
GET   /api/projects/{project_id}
PATCH /api/projects/{project_id}
```

### Run

```text
POST /api/projects/{project_id}/runs
POST /api/projects/{project_id}/continue
POST /api/projects/{project_id}/maintenance-runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/snapshot
GET  /api/runs/{run_id}/events
GET  /api/runs/{run_id}/trace
POST /api/runs/{run_id}/resume
POST /api/runs/{run_id}/recover
```

### Vault 和 ChangeSet

```text
POST /api/projects/{project_id}/vault/import
GET  /api/projects/{project_id}/vault
POST /api/projects/{project_id}/audits
GET  /api/projects/{project_id}/health
GET  /api/projects/{project_id}/maintenance-backlog
GET/POST /api/projects/{project_id}/change-sets
POST /approve
POST /apply
POST /rollback
```

### Retrieval 和知识增长

```text
GET  /api/config/retrieval
POST /api/projects/{project_id}/retrieval/reindex
POST /api/projects/{project_id}/chat
POST /api/projects/{project_id}/follow-up
POST /api/projects/{project_id}/exports
```

### 配置和资料

```text
LLM Config / Preset / Test
Search Config / Test
Source Registry Status
Document Create / Upload / Segment / Citation / Evidence Ingest
```

## Run 状态机

真实状态：

- Pending；
- Running；
- Waiting for Human；
- Interrupted；
- Completed；
- Failed。

前端不能把 Waiting 或 Interrupted 压缩成旧的 Progress Stage，否则用户会看到假 Running Spinner。

## SSE Event Stream

后端将 Trace 映射为 RunEvent：

- Thought；
- Action；
- Observation；
- State Update；
- Decision；
- Warning/Blocked；
- Artifact Created；
- Human Input Required。

前端 `useRunEvents` 使用 EventSource 连接 `/events`：

- Callback 使用 Ref，避免 React Render 导致重复重连；
- 使用 Timestamp + Gate + Event Type + Message Prefix 去重；
- `[DONE]` 时关闭连接；
- Idle Stream 使用 Keepalive，不制造假完成。

## Agent Heartbeat

LLM 决策可能持续几十秒。Runtime 每等待约 10 秒发一条 Thought Heartbeat，说明 Master 正在读取 State 和工具结果。

写作也按 Section 执行并发进度事件，避免用户误以为服务卡死。

## Snapshot

Run Snapshot 返回：

- Status 和 Current Stage；
- Terminal Reason；
- Resume/Recover 能力；
- Recovery Lineage；
- Progress；
- Search/Provider/Extraction/Writer Budget；
- Events 和 Errors；
- Artifact Summary。

前端以真实事件时间线作为主视图，Workflow Definition 只作为可展开的架构参考。

## SQLite 存储结构

核心表：

- projects；
- runs、run_events、user_inputs、run_state_checkpoints；
- evidence、evidence_fts；
- documents、document_segments、document_citations；
- artifacts；
- vault_imports；
- knowledge_health_reports；
- maintenance_tasks；
- change_sets；
- vector_index。

总共有 24 个迁移文件，数据库初始化会按顺序执行且保持幂等。

## Vector 存储

向量以 Float32 Byte Blob 写入 SQLite，同时保存 Dimension。读取后校验：

- Blob 长度与 Dimension 一致；
- Query Dimension 和 Index Dimension 一致；
- Similarity 是有限数值。

Dimension 或 Payload 异常时返回 `lexical_degraded`，提示 Rebuild，不继续声称 Hybrid。

## Artifact Supersession 的事务语义

`repository.add_artifact()` 在同一个 SQLite Connection 中：

1. 查询 Predecessor；
2. 新 Revision = 旧 Revision + 1；
3. 更新旧 Revision Active 和 Superseded By；
4. 插入新 Artifact。

这避免 Active Revision 链只更新一半。

## 前端工作台

主要能力：

- 创建新知识库 / 接管现有 Vault 双入口；
- LLM、Search、Extraction、Local RAG Readiness Matrix；
- 真实 Run Timeline 和 Budget；
- Vault Path 和记忆；
- Health Finding 和 Backlog；
- ChangeSet Diff、Evidence Gate、Base Hash 和 Conflict Recovery；
- Resume / Recover；
- Export 和打开受管 Vault；
- RAG Citation Provenance Badge。

为了控制首屏体积，Config、Knowledge Management 和 ReactFlow Panel 使用 Lazy Loading，主 Chunk 曾从约 639 kB 降到约 332 kB，Gzip 约 109 kB。

## API 幂等和并发控制示例

- 相同 Vault Snapshot Import 返回旧 Record；
- 相同 Audit Finding 通过 Fingerprint 去重 Task；
- 相同 Follow-up Question 复用 Active Page；
- Waiting Run Resume 使用 Compare-and-Set，重复请求返回 Conflict；
- Interrupted Run 只能创建一个 Recovery Child；
- Run Lease 防止旧 Worker 继续写。

## 面试回答：长时间 Agent 任务如何让用户可观察

> 我把一次研究抽象成持久化 Run，后端把 Thought、Action、Observation、State Update、错误、预算和 Artifact 事件写入 SQLite，再通过 SSE 增量推给前端。LLM 决策和长写作都有 Heartbeat，前端显示真实 Timeline，而不是只显示静态流程图。用户刷新页面后可以从 Run Snapshot 和历史事件恢复视图；Waiting 和 Interrupted 也有独立状态和操作。
